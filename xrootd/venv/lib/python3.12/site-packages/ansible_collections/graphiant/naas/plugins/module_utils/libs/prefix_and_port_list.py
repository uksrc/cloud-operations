"""
Prefix and Port List Manager for Graphiant Playbooks.

Prefix and port lists are configured under:
  edge.trafficPolicy.networkLists
  edge.trafficPolicy.portLists

Idempotency: create operations compare intended lists to current device state and skip
push when already matched.

Delete sets ``list: null`` per listed object (API nullable wrapper shape).

Per-list ``state: absent`` on create operations (``create_*``) also sends ``list: null`` for that
name only, so one YAML can mix present and absent entries.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from .base_manager import BaseManager
from .device_config_common import (
    as_dict,
    fetch_device_by_name,
    new_apply_result,
    push_device_config_raw,
    unwrap_device,
)
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()

_LOG_PREFIX = "[prefix-port-list]"
_TRAFFIC_POLICY_KEYS = ("trafficPolicy", "traffic_policy")
_NETWORK_LISTS_KEYS = ("networkLists", "network_lists")
_PORT_LISTS_KEYS = ("portLists", "port_lists")
_LIST_KINDS = frozenset({"both", "network", "port"})


class PrefixAndPortListManager(BaseManager):
    """Manage device-level network and L4 port lists via raw device-config payloads."""

    @classmethod
    def _device_dict(cls, device_info_dict: Any) -> Dict[str, Any]:
        return unwrap_device(as_dict(device_info_dict))

    @staticmethod
    def _first_present(mapping: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            if key in mapping:
                return mapping.get(key)
        return None

    @staticmethod
    def _validate_device_cfg(device_name: str, cfg: Any) -> Any:
        if cfg is None:
            return []
        if isinstance(cfg, (list, dict)):
            return cfg
        raise ConfigurationError(f"Device '{device_name}' config must be a list or dict of list objects")

    def _load_section(self, config_yaml_file: str, yaml_key: str) -> Dict[str, Any]:
        """
        Load ``{yaml_key: [{device_name: list_objects}, ...]}``.

        Device values are usually a list of prefix/port list dicts. The shared
        ``load_device_list_yaml_config`` helper only keeps dict-shaped device rows,
        so load this section directly.
        """
        cfg = self.render_config_file(config_yaml_file) or {}
        raw = cfg.get(yaml_key)
        by_name: Dict[str, Any] = {}
        if raw is None:
            return by_name
        if not isinstance(raw, list):
            raise ConfigurationError(f"'{yaml_key}' must be a list of device entries")
        for entry in raw:
            if not isinstance(entry, dict) or not entry:
                raise ConfigurationError(
                    f"Each entry in '{yaml_key}' must be a non-empty dict keyed by portal device name"
                )
            for device_name, device_cfg in entry.items():
                by_name[device_name] = self._validate_device_cfg(device_name, device_cfg)
        return by_name

    @staticmethod
    def _merge_partial_list_items(raw: List[Any]) -> List[Dict[str, Any]]:
        """
        Support YAML where a device entry is a list of partial dicts, e.g.::

            - name: demo_prefix_list_1
            - networks: [1.1.1.1/32]
        """
        merged: Dict[str, Any] = {}
        items: List[Dict[str, Any]] = []
        for part in raw:
            if not isinstance(part, dict):
                raise ConfigurationError("Each list entry must be a dict")
            if len(part) == 1 and "name" in part and len(merged) == 1 and "name" in merged:
                items.append(merged)
                merged = dict(part)
                continue
            if set(part.keys()).issubset({"name"}) and len(part) == 1:
                if merged:
                    items.append(merged)
                merged = dict(part)
                continue
            merged.update(part)
        if merged:
            items.append(merged)
        return items

    @classmethod
    def _normalize_list_items(cls, raw: Any, *, value_field: str) -> List[Dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            if raw.get("name") is not None or raw.get(value_field) is not None:
                return [dict(raw)]
            out: List[Dict[str, Any]] = []
            for name, body in raw.items():
                entry = {"name": str(name).strip()}
                if isinstance(body, dict):
                    entry.update(body)
                elif body is not None:
                    entry[value_field] = body
                out.append(entry)
            return out
        if isinstance(raw, list):
            if not raw:
                return []
            if all(isinstance(x, dict) and ("name" in x or value_field in x) for x in raw):
                if any(len(x) == 1 for x in raw):
                    return cls._merge_partial_list_items(raw)
                return [dict(x) for x in raw]
            raise ConfigurationError("List entries must be dicts with 'name' and/or list values")
        raise ConfigurationError("List config must be a list or dict")

    @staticmethod
    def _item_state(item: Dict[str, Any]) -> str:
        raw = item.get("state")
        if raw is None:
            return "present"
        return str(raw).strip().lower()

    @classmethod
    def _item_is_absent(cls, item: Dict[str, Any]) -> bool:
        return cls._item_state(item) == "absent"

    @staticmethod
    def _norm_networks(networks: Any) -> List[str]:
        if networks is None:
            return []
        if not isinstance(networks, list):
            raise ConfigurationError("'networks' must be a list of prefix strings")
        out: List[str] = []
        for net in networks:
            if net is None:
                continue
            s = str(net).strip()
            if s:
                out.append(s)
        return sorted(out)

    @staticmethod
    def _norm_ports(ports: Any) -> List[int]:
        if ports is None:
            return []
        if not isinstance(ports, list):
            raise ConfigurationError("'ports' must be a list of integers")
        out: List[int] = []
        for port in ports:
            if port is None:
                continue
            try:
                out.append(int(port))
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"Invalid port value {port!r}") from exc
        return sorted(out)

    @classmethod
    def _network_lists_from_yaml(cls, items: List[Dict[str, Any]], operation: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for item in items:
            name = item.get("name")
            if not name:
                raise ConfigurationError("Network list missing 'name'")
            key = str(name).strip()
            if not key:
                raise ConfigurationError("Network list 'name' must be non-empty")
            if operation == "delete" or cls._item_is_absent(item):
                out[key] = {"list": None}
                continue
            networks = cls._norm_networks(item.get("networks"))
            out[key] = {"list": {"name": key, "networks": networks}}
        return out

    @classmethod
    def _port_lists_from_yaml(cls, items: List[Dict[str, Any]], operation: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for item in items:
            name = item.get("name")
            if not name:
                raise ConfigurationError("Port list missing 'name'")
            key = str(name).strip()
            if not key:
                raise ConfigurationError("Port list 'name' must be non-empty")
            if operation == "delete" or cls._item_is_absent(item):
                out[key] = {"list": None}
                continue
            ports = cls._norm_ports(item.get("ports"))
            out[key] = {"list": {"name": key, "ports": ports}}
        return out

    @classmethod
    def _coerce_lists_map(cls, lists: Any, *, value_field: str) -> Dict[str, Any]:
        if not lists:
            return {}
        if isinstance(lists, dict):
            out: Dict[str, Any] = {}
            for key, entry in lists.items():
                if not isinstance(entry, dict):
                    continue
                body = entry.get("list") if "list" in entry else entry
                name = None
                if isinstance(body, dict):
                    name = body.get("name") or key
                elif body is None:
                    name = key
                if name:
                    out[str(name).strip()] = entry
            return out
        if isinstance(lists, list):
            out = {}
            for item in lists:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if name:
                    out[str(name).strip()] = {"list": item}
            return out
        return {}

    def _extract_lists_from_device(self, device_info_dict: Any, list_keys: Tuple[str, ...]) -> Dict[str, Any]:
        d = self._device_dict(device_info_dict)
        edge = as_dict(d.get("edge"))
        for container in (edge, d):
            tp = as_dict(self._first_present(container, _TRAFFIC_POLICY_KEYS))
            raw = self._first_present(tp, list_keys)
            if raw is not None:
                value_field = "networks" if list_keys == _NETWORK_LISTS_KEYS else "ports"
                return self._coerce_lists_map(raw, value_field=value_field)
        return {}

    @staticmethod
    def _existing_list_body(entry: Any) -> Any:
        if not isinstance(entry, dict):
            return None
        if "list" in entry:
            return entry.get("list")
        if any(k in entry for k in ("name", "networks", "ports")):
            return entry
        return None

    @classmethod
    def _normalized_network_list(cls, body: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(body, dict):
            return None
        name = body.get("name")
        if not name:
            return None
        return {"name": str(name).strip(), "networks": cls._norm_networks(body.get("networks"))}

    @classmethod
    def _normalized_port_list(cls, body: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(body, dict):
            return None
        name = body.get("name")
        if not name:
            return None
        return {"name": str(name).strip(), "ports": cls._norm_ports(body.get("ports"))}

    def _network_lists_need_update(self, desired: Dict[str, Any], device_info_dict: Any) -> bool:
        existing = self._extract_lists_from_device(device_info_dict, _NETWORK_LISTS_KEYS)
        for key, desired_entry in desired.items():
            desired_body = self._existing_list_body(desired_entry)
            existing_entry = existing.get(key) if isinstance(existing, dict) else None
            existing_body = self._existing_list_body(existing_entry)

            if desired_body is None:
                if existing_body is not None:
                    return True
                continue

            desired_norm = self._normalized_network_list(desired_body)
            existing_norm = self._normalized_network_list(existing_body)
            if desired_norm != existing_norm:
                return True
        return False

    def _port_lists_need_update(self, desired: Dict[str, Any], device_info_dict: Any) -> bool:
        existing = self._extract_lists_from_device(device_info_dict, _PORT_LISTS_KEYS)
        for key, desired_entry in desired.items():
            desired_body = self._existing_list_body(desired_entry)
            existing_entry = existing.get(key) if isinstance(existing, dict) else None
            existing_body = self._existing_list_body(existing_entry)

            if desired_body is None:
                if existing_body is not None:
                    return True
                continue

            desired_norm = self._normalized_port_list(desired_body)
            existing_norm = self._normalized_port_list(existing_body)
            if desired_norm != existing_norm:
                return True
        return False

    @classmethod
    def _snapshot_normalized_list_entry(cls, entry: Any, *, list_type: str) -> Optional[Dict[str, Any]]:
        body = cls._existing_list_body(entry)
        if body is None:
            return None
        if list_type == "network":
            return cls._normalized_network_list(body)
        return cls._normalized_port_list(body)

    def _traffic_policy_lists_diff(
        self, device_dict: Dict[str, Any], payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Build before/after snapshots for lists touched by this payload (for ``diff_plan`` / ``--diff``)."""
        desired_tp = as_dict(as_dict(payload.get("edge")).get("trafficPolicy"))
        before: Dict[str, Any] = {}
        after: Dict[str, Any] = {}

        desired_nl = desired_tp.get("networkLists")
        if isinstance(desired_nl, dict) and desired_nl:
            existing = self._extract_lists_from_device({"device": device_dict}, _NETWORK_LISTS_KEYS)
            before_nl: Dict[str, Any] = {}
            after_nl: Dict[str, Any] = {}
            for key in sorted(desired_nl.keys()):
                existing_entry = existing.get(key) if isinstance(existing, dict) else None
                before_nl[key] = self._snapshot_normalized_list_entry(existing_entry, list_type="network")
                after_nl[key] = self._snapshot_normalized_list_entry(desired_nl[key], list_type="network")
            before["networkLists"] = before_nl
            after["networkLists"] = after_nl

        desired_pl = desired_tp.get("portLists")
        if isinstance(desired_pl, dict) and desired_pl:
            existing = self._extract_lists_from_device({"device": device_dict}, _PORT_LISTS_KEYS)
            before_pl: Dict[str, Any] = {}
            after_pl: Dict[str, Any] = {}
            for key in sorted(desired_pl.keys()):
                existing_entry = existing.get(key) if isinstance(existing, dict) else None
                before_pl[key] = self._snapshot_normalized_list_entry(existing_entry, list_type="port")
                after_pl[key] = self._snapshot_normalized_list_entry(desired_pl[key], list_type="port")
            before["portLists"] = before_pl
            after["portLists"] = after_pl

        return before, after

    def _payload_differs(self, desired_payload: Dict[str, Any], device_info_dict: Any) -> bool:
        desired_tp = as_dict((desired_payload or {}).get("edge")).get("trafficPolicy") or {}
        if not isinstance(desired_tp, dict):
            desired_tp = {}

        desired_nl = desired_tp.get("networkLists")
        if isinstance(desired_nl, dict) and desired_nl:
            if self._network_lists_need_update(desired_nl, device_info_dict):
                return True

        desired_pl = desired_tp.get("portLists")
        if isinstance(desired_pl, dict) and desired_pl:
            if self._port_lists_need_update(desired_pl, device_info_dict):
                return True

        return False

    def _device_names_for_kind(self, config_yaml_file: str, list_kind: str) -> Set[str]:
        names: Set[str] = set()
        if list_kind in ("both", "network"):
            names.update(self._load_section(config_yaml_file, "networkLists").keys())
        if list_kind in ("both", "port"):
            names.update(self._load_section(config_yaml_file, "portLists").keys())
        return names

    def _build_device_payload(
        self,
        device_name: str,
        config_yaml_file: str,
        operation: str,
        list_kind: str,
    ) -> Optional[Dict[str, Any]]:
        traffic_policy: Dict[str, Any] = {}

        if list_kind in ("both", "network"):
            network_cfg = self._load_section(config_yaml_file, "networkLists").get(device_name)
            if network_cfg is not None:
                items = self._normalize_list_items(network_cfg, value_field="networks")
                network_map = self._network_lists_from_yaml(items, operation=operation)
                if network_map:
                    traffic_policy["networkLists"] = network_map

        if list_kind in ("both", "port"):
            port_cfg = self._load_section(config_yaml_file, "portLists").get(device_name)
            if port_cfg is not None:
                items = self._normalize_list_items(port_cfg, value_field="ports")
                port_map = self._port_lists_from_yaml(items, operation=operation)
                if port_map:
                    traffic_policy["portLists"] = port_map

        if not traffic_policy:
            return None
        return {"edge": {"trafficPolicy": traffic_policy}}

    def _iter_device_payloads(
        self,
        config_yaml_file: str,
        operation: str,
        list_kind: str,
    ) -> Iterator[Tuple[int, str, Dict[str, Any], Dict[str, Any]]]:
        if operation not in ("create", "delete"):
            raise ConfigurationError(f"Unsupported operation '{operation}'")
        if list_kind not in _LIST_KINDS:
            raise ConfigurationError(f"Unsupported list_kind '{list_kind}'")

        device_names = self._device_names_for_kind(config_yaml_file, list_kind)
        if not device_names:
            LOG.info("%s No devices to process in %s", _LOG_PREFIX, config_yaml_file)
            return

        enterprise = self.gsdk.enterprise_info["company_name"]
        for device_name in sorted(device_names):
            payload = self._build_device_payload(device_name, config_yaml_file, operation, list_kind)
            if not payload:
                LOG.info("%s No list entries for %s, skipping", _LOG_PREFIX, device_name)
                continue
            device_id, device_dict = fetch_device_by_name(self.gsdk, device_name, enterprise)
            yield device_id, device_name, payload, device_dict

    def apply_lists(self, config_yaml_file: str, operation: str, *, list_kind: str = "both") -> dict:
        result = new_apply_result()
        to_push: Dict[int, Dict[str, Any]] = {}
        configured_devices: List[str] = []
        diff_plan: List[Dict[str, Any]] = []

        for device_id, device_name, payload, device_dict in self._iter_device_payloads(
            config_yaml_file,
            operation=operation,
            list_kind=list_kind,
        ):
            if not self._payload_differs(payload, {"device": device_dict}):
                LOG.info("%s ✓ No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            before_tp, after_tp = self._traffic_policy_lists_diff(device_dict, payload)
            to_push[device_id] = {"device_id": device_id, "payload": payload}
            configured_devices.append(device_name)
            diff_plan.append(
                {
                    "device": device_name,
                    "branch": "edge.trafficPolicy",
                    "before": before_tp,
                    "after": after_tp,
                }
            )

        result["diff_plan"] = diff_plan
        if not to_push:
            return result

        push_device_config_raw(
            self.execute_concurrent_tasks,
            self.gsdk.put_device_config_raw,
            to_push,
            log_prefix=_LOG_PREFIX,
        )

        result["changed"] = True
        result["configured_devices"] = configured_devices
        return result

    def create_prefix_port_lists(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="create", list_kind="both")

    def delete_prefix_port_lists(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="delete", list_kind="both")

    def create_prefix_lists(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="create", list_kind="network")

    def delete_prefix_lists(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="delete", list_kind="network")

    def create_port_lists(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="create", list_kind="port")

    def delete_port_lists(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="delete", list_kind="port")

    def configure(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="create", list_kind="both")

    def deconfigure(self, config_yaml_file: str) -> dict:
        return self.apply_lists(config_yaml_file, operation="delete", list_kind="both")
