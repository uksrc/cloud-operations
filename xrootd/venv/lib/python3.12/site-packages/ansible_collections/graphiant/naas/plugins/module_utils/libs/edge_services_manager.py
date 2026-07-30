"""
Edge Services Manager for Graphiant Playbooks.

Configures edge-only services on ``PUT /v1/devices/{device_id}/config``:

- Device-level ``localWebServerPassword``
- Edge-level DNS mode (``DNSModeStatic``, ``DNSModeCloudflare``, ``DNSModeDynamic``)
- LAN interface ``lldpEnabled``
- LAN segment ``dhcpSubnets`` (key ``{interface}-{ipPrefix}``)
- Edge traffic policy ``dpiApplications`` (``edge.trafficPolicy.dpiApplications``)

YAML uses the ``edge_services`` list-of-single-key-dicts pattern (same as ``device_system``).
Configure-only; DHCP subnet removal uses ``state: absent`` (``subnet: null`` in the API payload).

LWS passwords are hashed in GET responses. Without ``localWebServerPasswordForce``, password is
pushed only when none is configured; with force, requires password from YAML, vault, or module params
(clear force after rotate). Diff uses ``localWebServerPasswordConfigured`` booleans.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .base_manager import BaseManager
from .device_config_common import (
    as_dict,
    coerce_str,
    fetch_device_by_name,
    load_device_list_yaml_config,
    new_apply_result,
    push_device_config_raw,
)
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()

_LOG_PREFIX = "[edge-services]"
_YAML_KEY = "edge_services"
_ALLOWED = frozenset(
    {
        "localWebServerPassword",
        "localWebServerPasswordForce",
        "dns",
        "lldp",
        "dhcpSubnets",
        "dpiApplications",
    }
)
_DNS_MODES = frozenset({"DNSModeStatic", "DNSModeCloudflare", "DNSModeDynamic"})
_LWS_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")
_TRAFFIC_POLICY_KEYS = ("trafficPolicy", "traffic_policy")
_DPI_PROTOCOLS = frozenset({"UnknownIPProtocol", "icmp", "tcp", "udp"})
_DPI_APP_FIELDS = (
    "name",
    "description",
    "ipProtocol",
    "sourceNetwork",
    "sourceNetworkList",
    "sourcePort",
    "sourcePortList",
    "destinationNetwork",
    "destinationNetworkList",
    "destinationPort",
    "destinationPortList",
)


class EdgeServicesManager(BaseManager):
    """Manage edge DHCP, DNS, LLDP, DPI applications, and local web server settings via the device config API."""

    _str = staticmethod(coerce_str)
    _as_dict = staticmethod(as_dict)

    @staticmethod
    def _first_present(mapping: Dict[str, Any], keys: tuple) -> Any:
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            if key in mapping:
                return mapping.get(key)
        return None

    @classmethod
    def _dhcp_subnet_key(cls, interface: Any, ip_prefix: Any) -> str:
        return f"{cls._str(interface)}-{cls._str(ip_prefix)}"

    @classmethod
    def _normalize_mac(cls, mac: Any) -> str:
        """Canonical MAC for compare/PUT (portal GET may return lowercase)."""
        return cls._str(mac).upper()

    @classmethod
    def _normalize_static_leases_from_get(cls, static_leases: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if isinstance(static_leases, list):
            for item in static_leases:
                if not isinstance(item, dict):
                    continue
                ip = cls._str(item.get("ipAddress"))
                mac = cls._normalize_mac(item.get("macAddress"))
                if ip and mac:
                    out[ip] = {"lease": {"ipAddress": ip, "macAddress": mac}}
        elif isinstance(static_leases, dict):
            for ip, body in static_leases.items():
                if not isinstance(body, dict):
                    continue
                lease = cls._as_dict(body.get("lease"))
                ip_addr = cls._str(lease.get("ipAddress")) or cls._str(ip)
                mac = cls._normalize_mac(lease.get("macAddress"))
                if ip_addr and mac:
                    out[cls._str(ip)] = {"lease": {"ipAddress": ip_addr, "macAddress": mac}}
        return out

    @classmethod
    def _normalize_static_leases_in_subnet(cls, subnet: Dict[str, Any]) -> None:
        """Normalize staticLeases MACs in-place on a subnet dict used for snapshots."""
        static = subnet.get("staticLeases")
        if not isinstance(static, dict):
            return
        normalized = cls._normalize_static_leases_from_get(static)
        if normalized:
            subnet["staticLeases"] = normalized
        elif "staticLeases" in subnet:
            del subnet["staticLeases"]

    @classmethod
    def _validate_lws_password(cls, password: str) -> None:
        if not _LWS_PASSWORD_RE.match(password):
            raise ConfigurationError(
                "localWebServerPassword must be at least 8 characters and include "
                "1 uppercase letter, 1 lowercase letter, and 1 digit."
            )

    @classmethod
    def _normalize_dhcp_subnet_from_get(cls, pool: Dict[str, Any]) -> Dict[str, Any]:
        ns = cls._as_dict(pool.get("nameservers"))
        ranges = pool.get("ranges") or []
        ip_range: List[Dict[str, str]] = []
        if isinstance(ranges, list):
            for r in ranges:
                if isinstance(r, dict) and r.get("start") and r.get("end"):
                    ip_range.append({"start": cls._str(r["start"]), "end": cls._str(r["end"])})
        out: Dict[str, Any] = {
            "ipPrefix": cls._str(pool.get("ipPrefix")),
            "interface": cls._str(pool.get("interface")),
            "name": cls._str(pool.get("name")),
            "description": cls._str(pool.get("description")),
            "ipGateway": cls._str(pool.get("gateway") or pool.get("ipGateway")),
            "defaultLeaseTimeSecs": pool.get("defaultLeaseTimeSecs"),
            "maxLeaseTimeSecs": pool.get("maxLeaseTimeSecs"),
            "minLeaseTimeSecs": pool.get("minLeaseTimeSecs"),
        }
        dn = cls._str(pool.get("domainName"))
        if dn:
            out["domainName"] = dn
        if ns:
            out["domainNameServer"] = {
                "primary": cls._str(ns.get("primary")),
                "secondary": cls._str(ns.get("secondary")),
            }
        if ip_range:
            out["ipRangesV2"] = {"ipRange": ip_range}
        static = cls._normalize_static_leases_from_get(pool.get("staticLeases"))
        if static:
            out["staticLeases"] = static
        return {k: v for k, v in out.items() if v not in (None, "", {}, [])}

    @classmethod
    def _normalize_dhcp_subnet_from_yaml(cls, subnet: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(subnet)
        if "ipGateway" not in out and out.get("gateway"):
            out["ipGateway"] = out.pop("gateway")
        if "domainNameServer" not in out and out.get("nameservers"):
            out["domainNameServer"] = out.pop("nameservers")
        if "ipRangesV2" not in out and out.get("ranges"):
            ranges = out.pop("ranges")
            if isinstance(ranges, list):
                out["ipRangesV2"] = {"ipRange": ranges}
        cls._normalize_static_leases_in_subnet(out)
        return {k: v for k, v in out.items() if v is not None}

    @classmethod
    def _dns_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        dns = cls._as_dict(d.get("dns"))
        mode = cls._str(dns.get("mode"))
        snap: Dict[str, Any] = {"mode": mode} if mode else {}
        if mode == "DNSModeStatic":
            v2 = cls._as_dict(dns.get("staticServersV2"))
            static: Dict[str, str] = {}
            for key, label in (
                ("primaryIpv4Server", "primaryIpv4"),
                ("primaryIpv6Server", "primaryIpv6"),
                ("secondaryIpv4Server", "secondaryIpv4"),
                ("secondaryIpv6Server", "secondaryIpv6"),
            ):
                srv = cls._as_dict(v2.get(key))
                addr = cls._str(srv.get("ipv4") or srv.get("ipv6"))
                if addr:
                    static[label] = addr
            if static:
                snap["static"] = static
        return snap

    @classmethod
    def _lldp_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, bool]:
        out: Dict[str, bool] = {}
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            name = cls._str(iface.get("name"))
            if not name:
                continue
            if iface.get("circuit") or iface.get("circuitName"):
                continue
            if "lldpEnabled" in iface:
                out[name] = bool(iface.get("lldpEnabled"))
        return out

    @classmethod
    def _lan_lldp_interface_names_from_device(cls, d: Dict[str, Any]) -> frozenset:
        """Portal hostnames for LAN interfaces (no circuit); LLDP applies to these only."""
        names: set = set()
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            name = cls._str(iface.get("name"))
            if not name:
                continue
            if iface.get("circuit") or iface.get("circuitName"):
                continue
            names.add(name)
        return frozenset(names)

    @classmethod
    def _validate_lldp_entries(cls, device_name: str, lldp_cfg: Dict[str, Any], current_device: Dict[str, Any]) -> None:
        """Require each lldp key to name a LAN interface (no WAN/circuit) on the device."""
        if not lldp_cfg:
            return
        lan_names = cls._lan_lldp_interface_names_from_device(current_device)
        all_names = cls._interface_names_from_device(current_device)
        for if_name in lldp_cfg:
            name = cls._str(if_name)
            if not name:
                continue
            if name in lan_names:
                continue
            known = (
                ", ".join(sorted(lan_names))
                if lan_names
                else "(none — configure LAN interfaces first, e.g. interface_management.yml --tags lan)"
            )
            if name not in all_names:
                raise ConfigurationError(
                    f"Device '{device_name}': lldp references interface {name!r} which does not exist "
                    f"on this device. Known LAN interfaces for LLDP: {known}."
                )
            raise ConfigurationError(
                f"Device '{device_name}': lldp references interface {name!r} which is not a LAN interface "
                f"(WAN/circuit interfaces cannot use LLDP). Known LAN interfaces: {known}."
            )

    @classmethod
    def _dhcp_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for seg in d.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            seg_name = cls._str(seg.get("name"))
            for pool in seg.get("dhcpSubnets") or []:
                if not isinstance(pool, dict):
                    continue
                iface = cls._str(pool.get("interface"))
                prefix = cls._str(pool.get("ipPrefix"))
                if not iface or not prefix:
                    continue
                key = cls._dhcp_subnet_key(iface, prefix)
                norm = cls._normalize_dhcp_subnet_from_get(pool)
                norm["segment"] = seg_name
                out[key] = norm
        return out

    @classmethod
    def _traffic_policy_from_device(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve ``trafficPolicy`` from unwrapped device GET (``device.edge`` or ``device``)."""
        edge = cls._as_dict(d.get("edge"))
        merged: Dict[str, Any] = {}
        for container in (edge, d):
            tp = cls._as_dict(cls._first_present(container, _TRAFFIC_POLICY_KEYS))
            if tp:
                merged.update(tp)
        return merged

    @classmethod
    def _list_names_from_traffic_policy(cls, tp: Dict[str, Any], list_keys: tuple) -> frozenset:
        raw = cls._first_present(tp, list_keys)
        if not raw:
            return frozenset()
        names: set[str] = set()
        if isinstance(raw, dict):
            for key, entry in raw.items():
                if not isinstance(entry, dict):
                    continue
                body = entry.get("list") if "list" in entry else entry
                if isinstance(body, dict) and body.get("name"):
                    names.add(cls._str(body.get("name")))
                elif body is not None:
                    names.add(cls._str(key))
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("name"):
                    names.add(cls._str(item.get("name")))
        return frozenset(n for n in names if n)

    @classmethod
    def _normalize_dpi_optional_str(cls, value: Any) -> Optional[str]:
        s = cls._str(value)
        return s if s else None

    @classmethod
    def _normalize_dpi_port(cls, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            port = int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid DPI port value {value!r}") from exc
        # Portal GET may return 0 for unset ports on icmp/any apps; treat as unset for compare/PUT.
        return None if port == 0 else port

    @classmethod
    def _normalize_dpi_application(cls, app: Dict[str, Any], app_key: Optional[str] = None) -> Dict[str, Any]:
        name = cls._str(app.get("name")) or cls._str(app_key)
        proto = cls._str(app.get("ipProtocol"))
        out: Dict[str, Any] = {
            "name": name,
            "description": app.get("description"),
            "ipProtocol": proto or None,
            "sourceNetwork": cls._normalize_dpi_optional_str(app.get("sourceNetwork")),
            "sourceNetworkList": cls._normalize_dpi_optional_str(app.get("sourceNetworkList")),
            "sourcePort": cls._normalize_dpi_port(app.get("sourcePort")),
            "sourcePortList": cls._normalize_dpi_optional_str(app.get("sourcePortList")),
            "destinationNetwork": cls._normalize_dpi_optional_str(app.get("destinationNetwork")),
            "destinationNetworkList": cls._normalize_dpi_optional_str(app.get("destinationNetworkList")),
            "destinationPort": cls._normalize_dpi_port(app.get("destinationPort")),
            "destinationPortList": cls._normalize_dpi_optional_str(app.get("destinationPortList")),
        }
        if out["description"] is not None and not cls._str(out["description"]):
            out["description"] = None
        return out

    @classmethod
    def _dpi_canonical_for_compare(cls, norm: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare only meaningful fields so sparse portal GET (omitted nulls) matches YAML with explicit nulls.
        """
        if not norm:
            return {}
        out: Dict[str, Any] = {}
        for key, value in norm.items():
            if key in ("name", "ipProtocol"):
                if value is not None:
                    out[key] = value
                continue
            if value is None:
                continue
            out[key] = value
        return out

    @classmethod
    def _dpi_compare_field_keys(cls, desired_app: Dict[str, Any]) -> frozenset:
        """Fields to compare: name/protocol always; other non-null keys present in YAML."""
        keys: set = {"name", "ipProtocol"}
        for field in _DPI_APP_FIELDS:
            if field in keys:
                continue
            if field in desired_app and desired_app.get(field) is not None:
                keys.add(field)
        return frozenset(keys)

    @classmethod
    def _dpi_canonical_subset(cls, norm: Dict[str, Any], keys: frozenset) -> Dict[str, Any]:
        canon = cls._dpi_canonical_for_compare(norm)
        return {key: canon[key] for key in keys if key in canon}

    @classmethod
    def _dpi_applications_equal(
        cls, before: Optional[Dict[str, Any]], desired_app: Dict[str, Any], app_key: str
    ) -> bool:
        norm_before = cls._normalize_dpi_application(before or {}, app_key=app_key) if before else {}
        norm_desired = cls._normalize_dpi_application(desired_app, app_key=app_key)
        keys = cls._dpi_compare_field_keys(desired_app)
        before_sub = cls._dpi_canonical_subset(norm_before, keys)
        desired_sub = cls._dpi_canonical_subset(norm_desired, keys)
        if before_sub == desired_sub:
            return True
        # Portal GET often omits ipProtocol after PUT even when YAML/API used UnknownIPProtocol.
        if norm_desired.get("ipProtocol") == "UnknownIPProtocol" and "ipProtocol" not in before_sub:
            keys_without_proto = frozenset(key for key in keys if key != "ipProtocol")
            return cls._dpi_canonical_subset(norm_before, keys_without_proto) == cls._dpi_canonical_subset(
                norm_desired, keys_without_proto
            )
        return False

    @classmethod
    def _extract_dpi_application_from_entry(
        cls, entry: Dict[str, Any], app_key: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Unwrap ``application`` or flat field dict; inject map key as name when omitted."""
        app = cls._as_dict(entry.get("application"))
        if not app and any(k in entry for k in _DPI_APP_FIELDS):
            app = dict(entry)
        if not app:
            return None
        if app_key and not cls._str(app.get("name")):
            app = dict(app)
            app["name"] = app_key
        return app

    @classmethod
    def _dpi_application_for_put(cls, app: Dict[str, Any], app_key: str) -> Dict[str, Any]:
        """Send non-null application fields listed in YAML (partial PUT delta)."""
        norm = cls._normalize_dpi_application(app, app_key=app_key)
        put: Dict[str, Any] = {"name": norm["name"], "ipProtocol": norm["ipProtocol"]}
        for field in _DPI_APP_FIELDS:
            if field in ("name", "ipProtocol"):
                continue
            if field in app and norm.get(field) is not None:
                put[field] = norm[field]
        return put

    @classmethod
    def _dpi_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Portal GET returns ``dpiApplications`` as a map or flat list under ``trafficPolicy``."""
        tp = cls._traffic_policy_from_device(d)
        raw = cls._first_present(tp, ("dpiApplications", "dpi_applications"))
        out: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                app_key = cls._str(entry.get("name"))
                if not app_key:
                    continue
                out[app_key] = cls._normalize_dpi_application(entry, app_key=app_key)
            return out
        if isinstance(raw, dict):
            for key, entry in raw.items():
                if not isinstance(entry, dict):
                    continue
                app = cls._as_dict(entry.get("application")) or entry
                app_key = cls._str(key) or cls._str(app.get("name"))
                if app_key:
                    out[app_key] = cls._normalize_dpi_application(app, app_key=app_key)
        return out

    @classmethod
    def _coerce_dpi_applications_map(cls, raw: Any) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Normalize YAML/module input to ``{app_name: application_dict}`` or ``{app_name: None}`` for removal.
        """
        if raw is None:
            return {}
        out: Dict[str, Optional[Dict[str, Any]]] = {}
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    raise ConfigurationError("Each dpiApplications list entry must be a dict.")
                app = cls._extract_dpi_application_from_entry(item)
                if not app:
                    raise ConfigurationError("dpiApplications list entries require an 'application' dict.")
                name = cls._str(app.get("name"))
                if not name:
                    raise ConfigurationError("dpiApplications application requires 'name'.")
                out[name] = app
            return out
        if not isinstance(raw, dict):
            raise ConfigurationError("dpiApplications must be a dict (map) or list of applications.")
        for app_key, body in raw.items():
            key = cls._str(app_key)
            if not key:
                raise ConfigurationError("dpiApplications map keys must be non-empty application names.")
            if body is None:
                out[key] = None
                continue
            if not isinstance(body, dict):
                raise ConfigurationError(f"dpiApplications entry {key!r} must be a dict.")
            state = cls._str(body.get("state") or "present").lower()
            if state == "absent":
                out[key] = None
                continue
            app = cls._extract_dpi_application_from_entry(body, app_key=key)
            if not app:
                raise ConfigurationError(
                    f"dpiApplications entry {key!r} requires an 'application' dict or application fields."
                )
            out[key] = app
        return out

    @classmethod
    def _validate_dpi_application(cls, app_key: str, app: Dict[str, Any]) -> None:
        explicit_name = cls._str(app.get("name"))
        if explicit_name and explicit_name != app_key:
            raise ConfigurationError(
                f"dpiApplications map key {app_key!r} must match application.name {explicit_name!r}."
            )
        norm = cls._normalize_dpi_application(app, app_key=app_key)
        proto = norm.get("ipProtocol")
        if proto not in _DPI_PROTOCOLS:
            raise ConfigurationError(
                f"dpiApplications {app_key!r}: ipProtocol must be one of {sorted(_DPI_PROTOCOLS)}."
            )

    @classmethod
    def _validate_dpi_list_references(
        cls,
        device_name: str,
        desired: Dict[str, Optional[Dict[str, Any]]],
        current_device: Dict[str, Any],
    ) -> None:
        desired = cls._coerce_dpi_applications_map(desired)
        tp = cls._traffic_policy_from_device(current_device)
        network_lists = cls._list_names_from_traffic_policy(tp, ("networkLists", "network_lists"))
        port_lists = cls._list_names_from_traffic_policy(tp, ("portLists", "port_lists"))
        for app_key, app in desired.items():
            if app is None:
                continue
            norm = cls._normalize_dpi_application(app, app_key=app_key)
            for field, known, label in (
                ("sourceNetworkList", network_lists, "networkLists"),
                ("destinationNetworkList", network_lists, "networkLists"),
                ("sourcePortList", port_lists, "portLists"),
                ("destinationPortList", port_lists, "portLists"),
            ):
                ref = norm.get(field)
                if ref and ref not in known:
                    known_str = ", ".join(sorted(known)) if known else "(none on device)"
                    raise ConfigurationError(
                        f"Device '{device_name}': dpiApplications {app_key!r} references "
                        f"{field}={ref!r} which is not in edge.trafficPolicy.{label}. "
                        f"Known names: {known_str}. Configure lists first (graphiant_prefix_port_list)."
                    )

    @classmethod
    def _edge_services_snapshot(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "localWebServerPasswordConfigured": bool(cls._str(d.get("localWebServerPassword"))),
            "dns": cls._dns_snapshot_from_device(d),
            "lldp": cls._lldp_snapshot_from_device(d),
            "dhcpSubnets": cls._dhcp_snapshot_from_device(d),
            "dpiApplications": cls._dpi_snapshot_from_device(d),
        }

    @classmethod
    def _build_dns_put(cls, dns_cfg: Dict[str, Any]) -> Dict[str, Any]:
        mode = cls._str(dns_cfg.get("mode"))
        if mode not in _DNS_MODES:
            raise ConfigurationError(f"dns.mode must be one of {sorted(_DNS_MODES)}.")
        inner: Dict[str, Any] = {}
        if mode == "DNSModeCloudflare":
            inner["cloudflare"] = {}
        elif mode == "DNSModeDynamic":
            inner["dynamic"] = dict(dns_cfg.get("dynamic") or {})
        elif mode == "DNSModeStatic":
            static_in = cls._as_dict(dns_cfg.get("static"))
            static_body: Dict[str, Any] = {}
            mapping = (
                ("primaryIpv4", "primaryIpv4V2"),
                ("primaryIpv6", "primaryIpv6V2"),
                ("secondaryIpv4", "secondaryIpv4V2"),
                ("secondaryIpv6", "secondaryIpv6V2"),
            )
            for yaml_key, api_key in mapping:
                val = cls._str(static_in.get(yaml_key))
                if val:
                    static_body[api_key] = {"address": val}
            if not static_body:
                raise ConfigurationError("dns.mode DNSModeStatic requires at least one static server address.")
            inner["static"] = static_body
        return {"dns": inner}

    @classmethod
    def _desired_dns_snapshot(cls, dns_cfg: Dict[str, Any]) -> Dict[str, Any]:
        mode = cls._str(dns_cfg.get("mode"))
        snap: Dict[str, Any] = {"mode": mode}
        if mode == "DNSModeStatic":
            static_in = cls._as_dict(dns_cfg.get("static"))
            static = {k: cls._str(v) for k, v in static_in.items() if cls._str(v)}
            if static:
                snap["static"] = static
        return snap

    @classmethod
    def _build_lldp_put(cls, lldp_map: Dict[str, bool]) -> Dict[str, Any]:
        interfaces: Dict[str, Any] = {}
        for if_name, enabled in sorted(lldp_map.items()):
            interfaces[if_name] = {"interface": {"lldpEnabled": bool(enabled)}}
        return {"interfaces": interfaces}

    @classmethod
    def _build_dhcp_put(cls, dhcp_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        segments: Dict[str, Any] = {}
        for entry in dhcp_entries:
            segment = cls._str(entry.get("segment"))
            iface = cls._str(entry.get("interface"))
            prefix = cls._str(entry.get("ipPrefix"))
            if not segment or not iface or not prefix:
                raise ConfigurationError("Each dhcpSubnets entry requires segment, interface, and ipPrefix.")
            key = cls._dhcp_subnet_key(iface, prefix)
            state = cls._str(entry.get("state") or "present").lower()
            seg_block = segments.setdefault(segment, {})
            dhcp_block = seg_block.setdefault("dhcpSubnets", {})
            if state == "absent":
                dhcp_block[key] = {"subnet": None}
                continue
            subnet_raw = cls._as_dict(entry.get("subnet"))
            if not subnet_raw:
                raise ConfigurationError(
                    f"dhcpSubnets entry {key} on segment {segment} requires a subnet dict when state is present."
                )
            subnet = cls._normalize_dhcp_subnet_from_yaml(subnet_raw)
            subnet.setdefault("ipPrefix", prefix)
            subnet.setdefault("interface", iface)
            dhcp_block[key] = {"subnet": subnet}
        return {"segments": segments}

    def _validate_cfg(self, device_name: str, cfg: Any) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        bad = set(cfg) - _ALLOWED
        if bad:
            raise ConfigurationError(
                f"Device '{device_name}' has unknown keys: {sorted(bad)}. Allowed: {sorted(_ALLOWED)}"
            )
        out = dict(cfg)
        pwd = out.get("localWebServerPassword")
        if pwd is not None:
            self._validate_lws_password(self._str(pwd))
        if out.get("dns") is not None:
            if not isinstance(out["dns"], dict):
                raise ConfigurationError(f"Device '{device_name}' dns must be a dict.")
            self._build_dns_put(out["dns"])
        if out.get("lldp") is not None:
            if not isinstance(out["lldp"], dict):
                raise ConfigurationError(f"Device '{device_name}' lldp must be a dict of interface names to bool.")
        if out.get("dhcpSubnets") is not None:
            if not isinstance(out["dhcpSubnets"], list):
                raise ConfigurationError(f"Device '{device_name}' dhcpSubnets must be a list.")
            for entry in out["dhcpSubnets"]:
                if not isinstance(entry, dict):
                    raise ConfigurationError("Each dhcpSubnets entry must be a dict.")
        if out.get("dpiApplications") is not None:
            desired_dpi = self._coerce_dpi_applications_map(out["dpiApplications"])
            for app_key, app in desired_dpi.items():
                if app is not None:
                    self._validate_dpi_application(app_key, app)
            out["dpiApplications"] = desired_dpi
        return out

    @staticmethod
    def _row_from_params(params: Dict[str, Any]) -> Dict[str, Any]:
        return {key: params[key] for key in _ALLOWED if params.get(key) is not None}

    @staticmethod
    def _merge_edge_services_override(merged: Dict[str, Any], ov: Dict[str, Any]) -> Dict[str, Any]:
        for k, v in ov.items():
            if k == "dhcpSubnets" and isinstance(merged.get("dhcpSubnets"), list) and isinstance(v, list):
                merged["dhcpSubnets"] = v
            elif k == "lldp" and isinstance(merged.get("lldp"), dict) and isinstance(v, dict):
                merged_lldp = dict(merged["lldp"])
                merged_lldp.update(v)
                merged["lldp"] = merged_lldp
            elif k == "dns" and isinstance(merged.get("dns"), dict) and isinstance(v, dict):
                merged_dns = dict(merged["dns"])
                merged_dns.update(v)
                merged["dns"] = merged_dns
            elif k == "dpiApplications" and isinstance(merged.get("dpiApplications"), dict) and isinstance(v, dict):
                merged_dpi = dict(merged["dpiApplications"])
                merged_dpi.update(v)
                merged["dpiApplications"] = merged_dpi
            else:
                merged[k] = v
        return merged

    def _load_edge_services(
        self, config_yaml_file: Optional[str], module_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            module_params,
            self.render_config_file,
            missing_input_error="Provide edge_services_config_file and/or device (portal device name).",
            build_row_from_params=self._row_from_params,
            merge_override=self._merge_edge_services_override,
            validate_device_cfg=self._validate_cfg,
        )

    def _assert_edge_device(self, device_name: str, d: Dict[str, Any]) -> None:
        role = self._str(d.get("role")).lower()
        if role == "core":
            raise ConfigurationError(
                f"Device '{device_name}' has role 'core'; edge services apply to Edge/Gateway (CPE) devices only."
            )

    @staticmethod
    def _log_no_edge_changes(device_name: str, device_id: int) -> None:
        """Log idempotent skip without referencing device config dicts (avoids secret taint in log sinks)."""
        LOG.info("%s No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)

    def _compute_after_snapshot(self, cfg: Dict[str, Any], before: Dict[str, Any]) -> Dict[str, Any]:
        after: Dict[str, Any] = {
            "localWebServerPasswordConfigured": before.get("localWebServerPasswordConfigured", False),
            "dns": dict(before.get("dns") or {}),
            "lldp": dict(before.get("lldp") or {}),
            "dhcpSubnets": dict(before.get("dhcpSubnets") or {}),
            "dpiApplications": dict(before.get("dpiApplications") or {}),
        }
        if cfg.get("localWebServerPassword") is not None:
            after["localWebServerPasswordConfigured"] = True
        if cfg.get("dns"):
            after["dns"] = self._desired_dns_snapshot(cfg["dns"])
        if cfg.get("lldp"):
            merged_lldp = dict(after["lldp"])
            merged_lldp.update({k: bool(v) for k, v in cfg["lldp"].items()})
            after["lldp"] = merged_lldp
        for entry in cfg.get("dhcpSubnets") or []:
            if not isinstance(entry, dict):
                continue
            key = self._dhcp_subnet_key(entry.get("interface"), entry.get("ipPrefix"))
            state = self._str(entry.get("state") or "present").lower()
            if state == "absent":
                after["dhcpSubnets"].pop(key, None)
                continue
            subnet = self._normalize_dhcp_subnet_from_yaml(self._as_dict(entry.get("subnet")))
            subnet["segment"] = self._str(entry.get("segment"))
            merged = dict(after["dhcpSubnets"].get(key) or {})
            merged.update(subnet)
            after["dhcpSubnets"][key] = merged
        desired_dpi = cfg.get("dpiApplications")
        if isinstance(desired_dpi, dict):
            merged_dpi = dict(after["dpiApplications"])
            for app_key, app in desired_dpi.items():
                if app is None:
                    merged_dpi.pop(app_key, None)
                else:
                    merged_dpi[app_key] = self._normalize_dpi_application(app, app_key=app_key)
            after["dpiApplications"] = merged_dpi
        return after

    @classmethod
    def _lan_segment_names_from_device(cls, d: Dict[str, Any]) -> frozenset:
        names: set[str] = set()
        for seg in d.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            nm = cls._str(seg.get("name"))
            if nm:
                names.add(nm)
        return frozenset(names)

    @classmethod
    def _interface_names_from_device(cls, d: Dict[str, Any]) -> frozenset:
        """Collect main and subinterface names from GET device (for DHCP validation)."""
        names: set[str] = set()
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            parent = cls._str(iface.get("name"))
            if parent:
                names.add(parent)
            subs = iface.get("subinterfaces")
            if isinstance(subs, dict):
                for vlan_key, sub in subs.items():
                    if parent and vlan_key is not None:
                        names.add(f"{parent}.{vlan_key}")
                    if isinstance(sub, dict):
                        sub_nm = cls._str(sub.get("name"))
                        if sub_nm:
                            names.add(sub_nm)
            elif isinstance(subs, list):
                for sub in subs:
                    if not isinstance(sub, dict):
                        continue
                    sub_nm = cls._str(sub.get("name"))
                    if sub_nm:
                        names.add(sub_nm)
                    elif parent and sub.get("vlan") is not None:
                        names.add(f"{parent}.{sub['vlan']}")
        for snap in cls._dhcp_snapshot_from_device(d).values():
            iface = cls._str(snap.get("interface"))
            if iface:
                names.add(iface)
        return frozenset(names)

    def _validate_dhcp_entries(
        self, device_name: str, dhcp_entries: List[Dict[str, Any]], current_device: Dict[str, Any]
    ) -> None:
        """Require segment and interface on each dhcpSubnets entry to exist on the device."""
        valid_segments = self._lan_segment_names_from_device(current_device)
        valid_interfaces = self._interface_names_from_device(current_device)
        for entry in dhcp_entries:
            if not isinstance(entry, dict):
                continue
            state = self._str(entry.get("state") or "present").lower()
            if state == "absent":
                continue
            seg = self._str(entry.get("segment"))
            if seg and seg not in valid_segments:
                known = (
                    ", ".join(sorted(valid_segments))
                    if valid_segments
                    else "(none — device has no LAN segments in GET response)"
                )
                raise ConfigurationError(
                    f"Device '{device_name}': dhcpSubnets references LAN segment {seg!r} which does not exist "
                    f"on this device. Known segment names: {known}."
                )
            iface = self._str(entry.get("interface"))
            if iface and iface not in valid_interfaces:
                known = (
                    ", ".join(sorted(valid_interfaces))
                    if valid_interfaces
                    else "(none — configure LAN interfaces first, e.g. interface_management.yml --tags lan)"
                )
                raise ConfigurationError(
                    f"Device '{device_name}': dhcpSubnets references interface {iface!r} which does not exist "
                    f"on this device. Known interfaces: {known}."
                )

    def _build_edge_payload(
        self, device_name: str, cfg: Dict[str, Any], current_device: Dict[str, Any]
    ) -> Dict[str, Any]:
        edge: Dict[str, Any] = {}

        if cfg.get("localWebServerPassword") is not None:
            force = bool(cfg.get("localWebServerPasswordForce"))
            if force or not self._str(current_device.get("localWebServerPassword")):
                edge["localWebServerPassword"] = cfg["localWebServerPassword"]

        if cfg.get("dns"):
            desired_dns = self._desired_dns_snapshot(cfg["dns"])
            current_dns = self._dns_snapshot_from_device(current_device)
            if desired_dns != current_dns:
                # API expects nested edge.dns.dns.{static|dynamic|cloudflare} (see PUT device config).
                edge["dns"] = self._build_dns_put(cfg["dns"])

        if cfg.get("lldp"):
            desired_lldp = {k: bool(v) for k, v in cfg["lldp"].items()}
            current_lldp = self._lldp_snapshot_from_device(current_device)
            delta = {k: v for k, v in desired_lldp.items() if current_lldp.get(k) != v}
            if delta:
                edge.update(self._build_lldp_put(delta))

        if cfg.get("dhcpSubnets"):
            self._validate_dhcp_entries(device_name, cfg["dhcpSubnets"], current_device)
            dhcp_delta: List[Dict[str, Any]] = []
            before_dhcp = self._dhcp_snapshot_from_device(current_device)
            for entry in cfg["dhcpSubnets"]:
                if not isinstance(entry, dict):
                    continue
                key = self._dhcp_subnet_key(entry.get("interface"), entry.get("ipPrefix"))
                state = self._str(entry.get("state") or "present").lower()
                if state == "absent":
                    if key in before_dhcp:
                        dhcp_delta.append(entry)
                    continue
                subnet_yaml = self._normalize_dhcp_subnet_from_yaml(self._as_dict(entry.get("subnet")))
                merged = dict(before_dhcp.get(key) or {})
                merged.update(subnet_yaml)
                if before_dhcp.get(key) != merged:
                    put_entry = dict(entry)
                    put_entry["subnet"] = merged
                    dhcp_delta.append(put_entry)
            if dhcp_delta:
                edge.update(self._build_dhcp_put(dhcp_delta))

        if cfg.get("dpiApplications"):
            desired_dpi = self._coerce_dpi_applications_map(cfg["dpiApplications"])
            self._validate_dpi_list_references(device_name, desired_dpi, current_device)
            before_dpi = self._dpi_snapshot_from_device(current_device)
            dpi_delta: Dict[str, Any] = {}
            for app_key, app in desired_dpi.items():
                if app is None:
                    if app_key in before_dpi:
                        dpi_delta[app_key] = {"application": None}
                    continue
                if not self._dpi_applications_equal(before_dpi.get(app_key), app, app_key):
                    dpi_delta[app_key] = {"application": self._dpi_application_for_put(app, app_key)}
            if dpi_delta:
                if edge.get("trafficPolicy"):
                    edge["trafficPolicy"]["dpiApplications"] = dpi_delta
                else:
                    edge["trafficPolicy"] = {"dpiApplications": dpi_delta}

        return edge

    def _inject_vault_lws_passwords(
        self, by_name: Dict[str, Dict[str, Any]], vault_lws: Optional[Dict[str, Any]]
    ) -> None:
        """Inject localWebServerPassword from vault dict keyed by portal device name."""
        if not vault_lws:
            return
        for device_name, cfg in by_name.items():
            if cfg.get("localWebServerPassword") is not None:
                continue
            pwd = self._str(vault_lws.get(device_name))
            if pwd:
                cfg["localWebServerPassword"] = pwd
                LOG.debug("%s Injected localWebServerPassword for %s from vault", _LOG_PREFIX, device_name)

    @classmethod
    def _validate_lws_password_sources(cls, by_name: Dict[str, Dict[str, Any]]) -> None:
        """Fail when force is set but no password is available after vault injection."""
        for device_name, cfg in by_name.items():
            if not cfg.get("localWebServerPasswordForce"):
                continue
            if not cls._str(cfg.get("localWebServerPassword")):
                raise ConfigurationError(
                    f"Device '{device_name}': localWebServerPasswordForce is true but "
                    "localWebServerPassword is missing. Set localWebServerPassword in YAML, "
                    "include a matching key in vault_devices_lws_password, or pass the password "
                    "via module parameters."
                )

    def apply_edge_services(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        vault_devices_lws_password: Optional[Dict[str, Any]] = None,
    ) -> dict:
        by_name = self._load_edge_services(config_yaml_file, module_params)
        self._inject_vault_lws_passwords(by_name, vault_devices_lws_password)
        self._validate_lws_password_sources(by_name)
        if not by_name:
            LOG.info("%s No '%s' entries to process", _LOG_PREFIX, _YAML_KEY)
            return new_apply_result(no_input=True)

        result = new_apply_result()
        to_push: Dict[int, Dict[str, Any]] = {}
        configured: List[str] = []
        diff_plan: List[Dict[str, Any]] = []
        enterprise = self.gsdk.enterprise_info["company_name"]

        for device_name, cfg in by_name.items():
            device_id, d = fetch_device_by_name(self.gsdk, device_name, enterprise)
            self._assert_edge_device(device_name, d)

            before = self._edge_services_snapshot(d)
            if cfg.get("lldp"):
                self._validate_lldp_entries(device_name, cfg["lldp"], d)
            edge_payload = self._build_edge_payload(device_name, cfg, d)
            after = self._compute_after_snapshot(cfg, before)
            if not edge_payload:
                self._log_no_edge_changes(device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            to_push[device_id] = {"device_id": device_id, "payload": {"edge": edge_payload}}
            configured.append(device_name)
            diff_plan.append({"device": device_name, "branch": "edge", "before": before, "after": after})

        if not to_push:
            return result

        push_device_config_raw(
            self.execute_concurrent_tasks,
            self.gsdk.put_device_config_raw,
            to_push,
            log_prefix=_LOG_PREFIX,
        )
        result["changed"] = True
        result["configured_devices"] = configured
        result["diff_plan"] = diff_plan
        return result

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        vault_devices_lws_password: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_edge_services(
            config_yaml_file=config_yaml_file,
            module_params=module_params,
            vault_devices_lws_password=vault_devices_lws_password,
        )

    def deconfigure(self, config_yaml_file: str) -> dict:
        raise ConfigurationError(
            "Deconfigure is not supported for edge services. "
            "Use configure with desired values, dhcpSubnets state: absent to remove a subnet, "
            "or dpiApplications state: absent (application: null) to remove a DPI application."
        )
