"""
MACsec Manager for Graphiant Playbooks.

Configures interface-level MACsec on ``PUT /v1/devices/{device_id}/config``:

- Ethernet interfaces under ``edge.interfaces.{name}.interface.macsec.macsec``
- LAG interfaces under ``edge.lagInterfaces.{name}.interface.macsec.macsec``

YAML uses the ``macsec`` list-of-single-key-dicts pattern (same as ``edge_services``).
Configure-only; PSK removal uses ``state: absent`` (``psk: null`` in the API payload).

CAK values are sensitive; use ``vault_devices_macsec_psk`` keyed by CKN (plaintext in YAML).
Diff redacts CAK values in snapshots (shows nickname and metadata only).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .base_manager import BaseManager
from .device_config_common import (
    as_dict,
    coerce_str,
    fetch_device_by_name,
    load_device_list_yaml_config,
    new_apply_result,
    push_device_config_raw,
    sdk_to_dict,
)
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()

_LOG_PREFIX = "[macsec]"
_YAML_KEY = "macsec"
_PSK_ROTATION_HINT = (
    " Add a new presharedKeys entry with a unique nickname, then remove the old key with "
    "state: absent. At least one key must remain."
)
_CAK_SUPPLY_HINT = (
    " Supply cak via: (1) cak in macsec YAML (dev/local), "
    "(2) cak on module parameters (dev/local), "
    "(3) vault_devices_macsec_psk (device → interface → ckn → cak; set ckn in YAML)."
)
_ALLOWED_DEVICE_KEYS = frozenset({"interfaces"})
_ALLOWED_INTERFACE_KEYS = frozenset(
    {
        "enabled",
        "encryptionEnforcementMode",
        "keyServerPriority",
        "presharedKeys",
        "sakConfiguration",
    }
)
_ALLOWED_PSK_KEYS = frozenset(
    {
        "nickname",
        "startTime",
        "cak",
        "ckn",
        "cipherSuite",
        "cakCryptographicAlgorithm",
        "useXpnForCipherSuite",
        "state",
    }
)
_ENCRYPTION_MODES = frozenset(
    {
        "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
        "MACSEC_ENFORCEMENT_MODE_SHOULD_ENCRYPT",
    }
)
_CIPHER_SUITES = frozenset({"AES_128_CMAC", "AES_256_CMAC"})
_CAK_HEX_LENGTH = {"AES_128_CMAC": 32, "AES_256_CMAC": 64}
# Backend/API supports at most three presharedKeys entries per MACsec interface.
_MAX_PSK_KEYS = 3
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_START_TIME_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


class MacsecManager(BaseManager):
    """Manage interface MACsec settings via the device config API."""

    _str = staticmethod(coerce_str)
    _as_dict = staticmethod(as_dict)

    @classmethod
    def _normalize_cipher_suite(cls, psk: Dict[str, Any]) -> str:
        alg = cls._str(psk.get("cakCryptographicAlgorithm")) or cls._str(psk.get("cipherSuite"))
        if alg not in _CIPHER_SUITES:
            raise ConfigurationError(
                f"presharedKeys entry {psk.get('nickname')!r}: cipherSuite / cakCryptographicAlgorithm "
                f"must be one of {sorted(_CIPHER_SUITES)}."
            )
        return alg

    @classmethod
    def _parse_start_time_datetime_string(cls, text: str) -> Optional[int]:
        """Parse UTC datetime strings such as ``2029-12-11 11:12:13`` into Unix seconds."""
        normalized = text.strip().rstrip("Zz")
        for fmt in _START_TIME_DATETIME_FORMATS:
            try:
                dt = datetime.strptime(normalized, fmt)
            except ValueError:
                continue
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        return None

    @classmethod
    def _normalize_start_time_seconds(cls, value: Any) -> int:
        if value is None:
            raise ConfigurationError("presharedKeys entry requires startTime (Unix seconds or UTC datetime string).")
        if isinstance(value, dict):
            seconds = value.get("seconds")
            if seconds is None:
                raise ConfigurationError("presharedKeys startTime requires seconds.")
            return int(seconds)
        if isinstance(value, bool):
            raise ConfigurationError("presharedKeys startTime must be Unix seconds or a UTC datetime string.")
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ConfigurationError("presharedKeys startTime cannot be empty.")
            if text.isdigit():
                return int(text)
            parsed = cls._parse_start_time_datetime_string(text)
            if parsed is not None:
                return parsed
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                "presharedKeys startTime must be Unix seconds or a UTC datetime string "
                f"(e.g. '2029-12-11 11:12:13'): {value!r}"
            ) from exc

    @classmethod
    def _validate_hex_field(cls, value: Any, *, field: str, min_len: int, max_len: int) -> str:
        text = cls._str(value)
        if not text:
            msg = f"{field} is required."
            if field == "cak":
                msg += _CAK_SUPPLY_HINT
            raise ConfigurationError(msg)
        if not _HEX_RE.match(text):
            raise ConfigurationError(f"{field} must be a hexadecimal string.")
        if len(text) < min_len or len(text) > max_len:
            raise ConfigurationError(f"{field} must be {min_len} to {max_len} hex digits.")
        return text.lower()

    @classmethod
    def _validate_psk_entry(cls, psk: Dict[str, Any], *, require_secrets: bool) -> Dict[str, Any]:
        nickname = cls._str(psk.get("nickname"))
        if not nickname:
            raise ConfigurationError("Each presharedKeys entry requires nickname.")
        state = cls._str(psk.get("state") or "present").lower()
        if state == "absent":
            return {"nickname": nickname, "state": "absent"}

        alg = cls._normalize_cipher_suite(psk)
        out: Dict[str, Any] = {
            "nickname": nickname,
            "startTime": cls._normalize_start_time_seconds(psk.get("startTime")),
            "cakCryptographicAlgorithm": alg,
            "state": "present",
        }
        if "useXpnForCipherSuite" in psk:
            out["useXpnForCipherSuite"] = bool(psk.get("useXpnForCipherSuite"))

        cak_len = _CAK_HEX_LENGTH[alg]
        if require_secrets or psk.get("cak") is not None:
            out["cak"] = cls._validate_hex_field(psk.get("cak"), field="cak", min_len=cak_len, max_len=cak_len)
        if require_secrets or psk.get("ckn") is not None:
            out["ckn"] = cls._validate_hex_field(psk.get("ckn"), field="ckn", min_len=2, max_len=64)

        if require_secrets and (not out.get("cak") or not out.get("ckn")):
            raise ConfigurationError(
                f"presharedKeys entry {nickname!r} requires cak and ckn when adding a new key." f"{_CAK_SUPPLY_HINT}"
            )
        return out

    @classmethod
    def _psk_rotation_required_message(cls, nickname: str) -> str:
        return (
            f"presharedKeys entry {nickname!r} already exists on the device; "
            f"PSK settings cannot be updated in place.{_PSK_ROTATION_HINT}"
        )

    @classmethod
    def _psk_yaml_entry_conflicts_with_current(
        cls,
        yaml_entry: Dict[str, Any],
        current_entry: Dict[str, Any],
    ) -> Optional[str]:
        """Return an error message when YAML attempts to change an existing PSK nickname in place."""
        if not current_entry:
            return None
        nickname = cls._str(yaml_entry.get("nickname"))
        if "startTime" in yaml_entry:
            yaml_start = cls._normalize_start_time_seconds(yaml_entry.get("startTime"))
            if yaml_start != current_entry.get("startTime"):
                return cls._psk_rotation_required_message(nickname)
        if "ckn" in yaml_entry:
            yaml_ckn = cls._str(yaml_entry.get("ckn")).lower()
            if yaml_ckn != cls._str(current_entry.get("ckn")).lower():
                return cls._psk_rotation_required_message(nickname)
        if "cipherSuite" in yaml_entry or "cakCryptographicAlgorithm" in yaml_entry:
            if cls._normalize_cipher_suite(yaml_entry) != current_entry.get("cakCryptographicAlgorithm"):
                return cls._psk_rotation_required_message(nickname)
        if "useXpnForCipherSuite" in yaml_entry:
            yaml_xpn = bool(yaml_entry.get("useXpnForCipherSuite"))
            if yaml_xpn != bool(current_entry.get("useXpnForCipherSuite")):
                return cls._psk_rotation_required_message(nickname)
        return None

    @classmethod
    def _normalize_sak_from_get(cls, sak_list: Any) -> Dict[str, Any]:
        if not isinstance(sak_list, list) or not sak_list:
            return {}
        first = sak_list[0]
        if not isinstance(first, dict):
            return {}
        out: Dict[str, Any] = {}
        if first.get("rekeyInterval") is not None:
            out["rekeyInterval"] = int(first["rekeyInterval"])
        if first.get("replayProtectionWindowSize") is not None:
            out["replayProtectionWindowSize"] = int(first["replayProtectionWindowSize"])
        return out

    @classmethod
    def _normalize_psk_from_get(cls, psk_list: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not isinstance(psk_list, list):
            return out
        for item in psk_list:
            if not isinstance(item, dict):
                continue
            nickname = cls._str(item.get("nickname"))
            if not nickname:
                continue
            entry: Dict[str, Any] = {
                "nickname": nickname,
                "startTime": cls._normalize_start_time_seconds(item.get("startTime")),
                "cakCryptographicAlgorithm": cls._str(item.get("cakCryptographicAlgorithm")),
                "ckn": cls._str(item.get("ckn")),
            }
            if item.get("cak"):
                entry["cak"] = cls._str(item.get("cak")).lower()
            if "useXpnForCipherSuite" in item:
                entry["useXpnForCipherSuite"] = bool(item.get("useXpnForCipherSuite"))
            out[nickname] = entry
        return out

    @classmethod
    def _interface_catalog_from_device(cls, d: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Map main interface name -> {type, macsec snapshot}. Subinterfaces are excluded."""
        catalog: Dict[str, Dict[str, Any]] = {}
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            name = cls._str(iface.get("name"))
            if not name:
                continue
            iface_type = cls._str(iface.get("type")).lower() or "ethernet"
            macsec_raw = cls._as_dict(iface.get("macsec"))
            catalog[name] = {
                "type": iface_type,
                "macsec": cls._macsec_snapshot_from_block(macsec_raw),
            }
        return catalog

    @classmethod
    def _macsec_snapshot_from_block(cls, macsec_raw: Dict[str, Any]) -> Dict[str, Any]:
        enabled_raw = macsec_raw.get("enabled")
        key_server_priority = macsec_raw.get("keyServerPriority")
        snap: Dict[str, Any] = {
            "enabled": bool(enabled_raw) if enabled_raw is not None else False,
            "encryptionEnforcementMode": cls._str(macsec_raw.get("encryptionEnforcementMode")),
            "keyServerPriority": (int(key_server_priority) if key_server_priority is not None else None),
            "presharedKeys": cls._normalize_psk_from_get(macsec_raw.get("pskConfigurations")),
            "sakConfiguration": cls._normalize_sak_from_get(macsec_raw.get("sakConfigurations")),
        }
        return {k: v for k, v in snap.items() if v not in (None, "", {}, []) or k == "enabled"}

    @classmethod
    def _macsec_snapshot_for_device(cls, d: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        catalog = cls._interface_catalog_from_device(d)
        return {name: info["macsec"] for name, info in catalog.items() if info.get("macsec")}

    @classmethod
    def _redact_psk_for_diff(cls, psk_map: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        redacted: Dict[str, Dict[str, Any]] = {}
        for nick, psk in sorted(psk_map.items()):
            entry = {k: v for k, v in psk.items() if k != "cak"}
            if psk.get("cak"):
                entry["cakConfigured"] = True
            redacted[nick] = entry
        return redacted

    @classmethod
    def _redact_interface_snapshot(cls, snap: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(snap)
        if isinstance(out.get("presharedKeys"), dict):
            out["presharedKeys"] = cls._redact_psk_for_diff(out["presharedKeys"])
        return out

    @classmethod
    def _normalize_sak_from_yaml(cls, sak: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if sak.get("replayProtectionWindowSize") is not None:
            out["replayProtectionWindowSize"] = int(sak["replayProtectionWindowSize"])
        if sak.get("rekeyInterval") is not None:
            out["rekeyInterval"] = int(sak["rekeyInterval"])
        return out

    @classmethod
    def _validate_interface_entries(
        cls, device_name: str, interfaces_cfg: Dict[str, Any], current_device: Dict[str, Any]
    ) -> None:
        catalog = cls._interface_catalog_from_device(current_device)
        for if_name in interfaces_cfg:
            name = cls._str(if_name)
            if not name:
                continue
            if name not in catalog:
                known = ", ".join(sorted(catalog)) if catalog else "(none — configure interfaces first)"
                raise ConfigurationError(
                    f"Device '{device_name}': interfaces references {name!r} which does not exist "
                    f"on this device. Known main interfaces: {known}."
                )
            iface_type = catalog[name]["type"]
            if iface_type not in ("ethernet", "lag"):
                raise ConfigurationError(
                    f"Device '{device_name}': MACsec on interface {name!r} with type {iface_type!r} "
                    "is not supported (only ethernet and lag main interfaces)."
                )

    def _validate_cfg(self, device_name: str, cfg: Any) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        bad = set(cfg) - _ALLOWED_DEVICE_KEYS
        if bad:
            raise ConfigurationError(
                f"Device '{device_name}' has unknown keys: {sorted(bad)}. Allowed: {sorted(_ALLOWED_DEVICE_KEYS)}"
            )
        interfaces = cfg.get("interfaces")
        if interfaces is None:
            raise ConfigurationError(f"Device '{device_name}' requires interfaces.")
        if not isinstance(interfaces, dict) or not interfaces:
            raise ConfigurationError(f"Device '{device_name}' interfaces must be a non-empty dict.")

        validated_interfaces: Dict[str, Any] = {}
        for if_name, if_cfg in interfaces.items():
            name = self._str(if_name)
            if not isinstance(if_cfg, dict):
                raise ConfigurationError(f"Device '{device_name}' interface {name!r} config must be a dict.")
            bad_if = set(if_cfg) - _ALLOWED_INTERFACE_KEYS
            if bad_if:
                raise ConfigurationError(
                    f"Device '{device_name}' interface {name!r} has unknown keys: {sorted(bad_if)}."
                )
            out_if: Dict[str, Any] = {}
            if "enabled" in if_cfg:
                out_if["enabled"] = bool(if_cfg["enabled"])
            mode = self._str(if_cfg.get("encryptionEnforcementMode"))
            if mode:
                if mode not in _ENCRYPTION_MODES:
                    raise ConfigurationError(
                        f"Device '{device_name}' interface {name!r}: encryptionEnforcementMode must be one of "
                        f"{sorted(_ENCRYPTION_MODES)}."
                    )
                out_if["encryptionEnforcementMode"] = mode
            if if_cfg.get("keyServerPriority") is not None:
                out_if["keyServerPriority"] = int(if_cfg["keyServerPriority"])
            if if_cfg.get("sakConfiguration") is not None:
                if not isinstance(if_cfg["sakConfiguration"], dict):
                    raise ConfigurationError(
                        f"Device '{device_name}' interface {name!r}: sakConfiguration must be a dict."
                    )
                out_if["sakConfiguration"] = self._normalize_sak_from_yaml(if_cfg["sakConfiguration"])
            if if_cfg.get("presharedKeys") is not None:
                if not isinstance(if_cfg["presharedKeys"], list):
                    raise ConfigurationError(
                        f"Device '{device_name}' interface {name!r}: presharedKeys must be a list."
                    )
                psk_out: List[Dict[str, Any]] = []
                for psk in if_cfg["presharedKeys"]:
                    if not isinstance(psk, dict):
                        raise ConfigurationError("Each presharedKeys entry must be a dict.")
                    bad_psk = set(psk) - _ALLOWED_PSK_KEYS
                    if bad_psk:
                        raise ConfigurationError(f"presharedKeys entry has unknown keys: {sorted(bad_psk)}.")
                    psk_out.append(self._validate_psk_entry(psk, require_secrets=False))
                out_if["presharedKeys"] = psk_out
            validated_interfaces[name] = out_if
        return {"interfaces": validated_interfaces}

    @staticmethod
    def _row_from_params(params: Dict[str, Any]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        if params.get("interfaces") is not None:
            row["interfaces"] = params["interfaces"]
        return row

    @staticmethod
    def _merge_macsec_override(merged: Dict[str, Any], ov: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in ov.items():
            if key == "interfaces" and isinstance(merged.get("interfaces"), dict) and isinstance(value, dict):
                merged_if = dict(merged["interfaces"])
                for if_name, if_cfg in value.items():
                    if if_name in merged_if and isinstance(merged_if[if_name], dict) and isinstance(if_cfg, dict):
                        base = dict(merged_if[if_name])
                        if "presharedKeys" in if_cfg:
                            base["presharedKeys"] = if_cfg["presharedKeys"]
                        else:
                            for psk_key in (
                                "enabled",
                                "encryptionEnforcementMode",
                                "keyServerPriority",
                                "sakConfiguration",
                            ):
                                if psk_key in if_cfg:
                                    base[psk_key] = if_cfg[psk_key]
                        merged_if[if_name] = base
                    else:
                        merged_if[if_name] = if_cfg
                merged["interfaces"] = merged_if
            else:
                merged[key] = value
        return merged

    def _load_macsec(
        self, config_yaml_file: Optional[str], module_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            module_params,
            self.render_config_file,
            missing_input_error="Provide macsec_config_file and/or device (portal device name).",
            build_row_from_params=self._row_from_params,
            merge_override=self._merge_macsec_override,
            validate_device_cfg=self._validate_cfg,
        )

    def _assert_edge_device(self, device_name: str, d: Dict[str, Any]) -> None:
        role = self._str(d.get("role")).lower()
        if role == "core":
            raise ConfigurationError(
                f"Device '{device_name}' has role 'core'; MACsec applies to Edge/Gateway (CPE) devices only."
            )

    @classmethod
    def _validate_psk_limit(cls, psk_map: Dict[str, Dict[str, Any]]) -> None:
        if len(psk_map) > _MAX_PSK_KEYS:
            raise ConfigurationError(f"At most {_MAX_PSK_KEYS} presharedKeys are allowed per interface.")

    @classmethod
    def _compute_desired_psk_map(
        cls,
        current_psk: Dict[str, Dict[str, Any]],
        psk_entries: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        desired = dict(current_psk)
        for entry in psk_entries:
            nick = cls._str(entry.get("nickname"))
            state = cls._str(entry.get("state") or "present").lower()
            if state == "absent":
                desired.pop(nick, None)
                continue
            merged = dict(desired.get(nick) or {})
            merged.update(entry)
            merged.pop("state", None)
            if merged.get("cipherSuite") or merged.get("cakCryptographicAlgorithm"):
                merged["cakCryptographicAlgorithm"] = cls._normalize_cipher_suite(merged)
                merged.pop("cipherSuite", None)
            desired[nick] = merged
        cls._validate_psk_limit(desired)
        return desired

    @classmethod
    def _compute_desired_interface_snapshot(
        cls,
        current: Dict[str, Any],
        desired_cfg: Dict[str, Any],
    ) -> Dict[str, Any]:
        after = dict(current)
        if "enabled" in desired_cfg:
            after["enabled"] = bool(desired_cfg["enabled"])
        if desired_cfg.get("encryptionEnforcementMode"):
            after["encryptionEnforcementMode"] = desired_cfg["encryptionEnforcementMode"]
        if desired_cfg.get("keyServerPriority") is not None:
            after["keyServerPriority"] = int(desired_cfg["keyServerPriority"])
        if desired_cfg.get("sakConfiguration"):
            merged_sak = dict(after.get("sakConfiguration") or {})
            merged_sak.update(desired_cfg["sakConfiguration"])
            after["sakConfiguration"] = merged_sak
        if desired_cfg.get("presharedKeys"):
            after["presharedKeys"] = cls._compute_desired_psk_map(
                after.get("presharedKeys") or {},
                desired_cfg["presharedKeys"],
            )
        return after

    @classmethod
    def _psk_put_entry(cls, psk: Dict[str, Any]) -> Dict[str, Any]:
        alg = psk.get("cakCryptographicAlgorithm") or cls._normalize_cipher_suite(psk)
        body: Dict[str, Any] = {
            "nickname": psk["nickname"],
            "startTime": {
                "seconds": cls._normalize_start_time_seconds(psk["startTime"]),
                "nanos": 0,
            },
            "cak": psk["cak"],
            "ckn": psk["ckn"],
            "cakCryptographicAlgorithm": alg,
        }
        if "useXpnForCipherSuite" in psk:
            body["useXpnForCipherSuite"] = bool(psk["useXpnForCipherSuite"])
        return {"psk": body}

    @classmethod
    def _build_sak_put(cls, sak_delta: Dict[str, Any]) -> Dict[str, Any]:
        sak: Dict[str, Any] = {}
        if "replayProtectionWindowSize" in sak_delta:
            sak["nullableReplayProtectionWindowSize"] = {
                "replayProtectionWindowSize": int(sak_delta["replayProtectionWindowSize"])
            }
        if "rekeyInterval" in sak_delta:
            sak["nullableRekeyInterval"] = {"rekeyInterval": int(sak_delta["rekeyInterval"])}
        return {"globalSakConfiguration": {"sak": sak}}

    @classmethod
    def _psk_put_map_from_snapshot(
        cls,
        psk_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build pskConfigurationsByNickname for PUT from a merged PSK snapshot."""
        psk_put: Dict[str, Any] = {}
        for _nickname, merged in sorted(psk_map.items()):
            if merged.get("cak") and merged.get("ckn"):
                psk_put[merged["nickname"]] = cls._psk_put_entry(merged)
        return psk_put

    @classmethod
    def _expand_macsec_put_for_sdk(
        cls,
        delta: Dict[str, Any],
        current: Dict[str, Any],
        after: Dict[str, Any],
    ) -> None:
        """
        Pad a partial MACsec PUT delta so graphiant_sdk pydantic validation succeeds.

        OpenAPI documents partial merge PUTs (UI sends only changed fields). The Python SDK
        still validates ``manaV2MaCsecConfiguration`` as a complete object when constructing
        ``V1DevicesDeviceIdConfigPutRequest``. Missing OpenAPI required properties are filled
        from the merged snapshot here — only at push time, not for change detection.
        """
        snapshot = after or current

        if "enabled" not in delta:
            delta["enabled"] = bool(snapshot.get("enabled"))

        if "encryptionEnforcementMode" not in delta:
            mode = snapshot.get("encryptionEnforcementMode")
            if mode:
                delta["encryptionEnforcementMode"] = mode

        if "globalSakConfiguration" not in delta:
            sak_cfg = snapshot.get("sakConfiguration") or {}
            delta.update(cls._build_sak_put(sak_cfg) if sak_cfg else {"globalSakConfiguration": {"sak": {}}})

        if "pskConfigurationsByNickname" not in delta:
            delta["pskConfigurationsByNickname"] = {}

        delta.setdefault("sakConfigurationsByLagMemberInterfaceId", {})

    @classmethod
    def _expand_macsec_edge_payload_for_sdk(
        cls,
        edge: Dict[str, Any],
        before_by_interface: Dict[str, Dict[str, Any]],
        after_by_interface: Dict[str, Dict[str, Any]],
    ) -> None:
        for branch in ("interfaces", "lagInterfaces"):
            for if_name, wrap in (edge.get(branch) or {}).items():
                macsec = ((wrap.get("interface") or {}).get("macsec") or {}).get("macsec")
                if not isinstance(macsec, dict) or not macsec:
                    continue
                current = before_by_interface.get(if_name) or {}
                after = after_by_interface.get(if_name) or {}
                cls._expand_macsec_put_for_sdk(macsec, current, after)

    @classmethod
    def _build_interface_macsec_put(
        cls,
        desired_cfg: Dict[str, Any],
        current: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Return (api_macsec_delta, desired_snapshot_after_merge)."""
        after = cls._compute_desired_interface_snapshot(current, desired_cfg)
        delta: Dict[str, Any] = {}

        if "enabled" in desired_cfg and bool(current.get("enabled")) != bool(after.get("enabled")):
            delta["enabled"] = bool(after.get("enabled"))

        if desired_cfg.get("encryptionEnforcementMode"):
            if current.get("encryptionEnforcementMode") != after.get("encryptionEnforcementMode"):
                delta["encryptionEnforcementMode"] = after["encryptionEnforcementMode"]

        if desired_cfg.get("keyServerPriority") is not None:
            if current.get("keyServerPriority") != after.get("keyServerPriority"):
                delta["keyServerPriority"] = after["keyServerPriority"]

        if desired_cfg.get("sakConfiguration"):
            current_sak = current.get("sakConfiguration") or {}
            desired_sak = after.get("sakConfiguration") or {}
            sak_delta = {
                key: desired_sak[key]
                for key in desired_cfg["sakConfiguration"]
                if current_sak.get(key) != desired_sak.get(key)
            }
            if sak_delta:
                delta.update(cls._build_sak_put(sak_delta))

        if desired_cfg.get("presharedKeys"):
            current_psk = current.get("presharedKeys") or {}
            desired_psk = after.get("presharedKeys") or {}
            psk_put: Dict[str, Any] = {}
            for psk in desired_cfg["presharedKeys"]:
                nickname = cls._str(psk.get("nickname"))
                state = cls._str(psk.get("state") or "present").lower()
                if state == "absent":
                    if nickname in current_psk:
                        psk_put[nickname] = {"psk": None}
                    continue
                current_entry = current_psk.get(nickname) or {}
                if not current_entry:
                    merged = desired_psk.get(nickname) or {}
                    if not merged.get("cak") or not merged.get("ckn"):
                        raise ConfigurationError(
                            f"presharedKeys entry {nickname!r} requires cak and ckn when adding a new key."
                            f"{_CAK_SUPPLY_HINT}"
                        )
                    psk_put[nickname] = cls._psk_put_entry(merged)
                    continue
                conflict = cls._psk_yaml_entry_conflicts_with_current(psk, current_entry)
                if conflict:
                    raise ConfigurationError(conflict)
            if psk_put:
                delta["pskConfigurationsByNickname"] = psk_put

        enabled_after = bool(after.get("enabled"))
        if enabled_after and not after.get("presharedKeys"):
            raise ConfigurationError(
                "MACsec cannot be enabled without at least one presharedKeys entry; "
                "the API requires at least one PSK configuration."
            )
        if enabled_after:
            cls._validate_psk_limit(after.get("presharedKeys") or {})

        return delta, after

    def _build_edge_payload(
        self,
        device_name: str,
        cfg: Dict[str, Any],
        current_device: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        catalog = self._interface_catalog_from_device(current_device)
        self._validate_interface_entries(device_name, cfg["interfaces"], current_device)

        edge: Dict[str, Any] = {}
        after_by_interface: Dict[str, Dict[str, Any]] = {}

        for if_name, if_cfg in cfg["interfaces"].items():
            name = self._str(if_name)
            current = catalog.get(name, {}).get("macsec") or {
                "enabled": False,
                "presharedKeys": {},
                "sakConfiguration": {},
            }
            delta, after = self._build_interface_macsec_put(if_cfg, current)
            if not delta:
                continue
            iface_type = catalog[name]["type"]
            branch_key = "lagInterfaces" if iface_type == "lag" else "interfaces"
            edge.setdefault(branch_key, {})[name] = {"interface": {"macsec": {"macsec": delta}}}
            after_by_interface[name] = after

        return edge, after_by_interface

    @classmethod
    def _cak_from_vault_entry(cls, entry: Any) -> str:
        """Return CAK hex from a vault entry (plain string or dict with cak)."""
        if isinstance(entry, str) and entry.strip():
            return cls._str(entry).lower()
        if isinstance(entry, dict):
            cak = cls._str(entry.get("cak"))
            if cak:
                return cak.lower()
        return ""

    @classmethod
    def _lookup_vault_cak_by_ckn(cls, if_vault: Dict[str, Any], ckn: str) -> str:
        """Look up CAK in interface vault map; vault CKN keys are matched case-insensitively."""
        if not ckn or not isinstance(if_vault, dict):
            return ""
        ckn_lower = ckn.lower()
        entry = if_vault.get(ckn_lower)
        if entry is None:
            for key, val in if_vault.items():
                if cls._str(key).lower() == ckn_lower:
                    entry = val
                    break
        return cls._cak_from_vault_entry(entry)

    @classmethod
    def _format_vault_cak_lookup_failure(
        cls,
        device_name: str,
        if_name: str,
        nickname: str,
        ckn: str,
        vault_psk: Optional[Dict[str, Any]],
    ) -> str:
        """Explain why vault_devices_macsec_psk did not supply CAK for this PSK entry."""
        header = (
            f"CAK is required for device {device_name!r}, interface {if_name!r}, "
            f"presharedKeys nickname {nickname!r}, ckn {ckn!r}."
        )
        if not vault_psk:
            detail = "vault_devices_macsec_psk was not provided or is empty."
        else:
            device_vault = vault_psk.get(device_name)
            if not isinstance(device_vault, dict):
                known_devices = sorted(cls._str(k) for k in vault_psk)
                detail = (
                    f"vault_devices_macsec_psk has no entry for device {device_name!r}."
                    f" Known device keys: {known_devices!r}."
                )
            else:
                if_vault = device_vault.get(if_name)
                if not isinstance(if_vault, dict):
                    known_interfaces = sorted(cls._str(k) for k in device_vault)
                    detail = (
                        f"vault_devices_macsec_psk has no entry for interface {if_name!r} "
                        f"on device {device_name!r}. Known interface keys: {known_interfaces!r}."
                    )
                else:
                    known_ckns = sorted(cls._str(k) for k in if_vault)
                    detail = (
                        f"vault_devices_macsec_psk has no CAK for ckn {ckn!r} on "
                        f"device {device_name!r}, interface {if_name!r}."
                        f" Known ckn keys on that interface: {known_ckns!r}."
                    )
        return f"{header} {detail}{_CAK_SUPPLY_HINT}"

    def _inject_vault_psk_secrets(
        self,
        by_name: Dict[str, Dict[str, Any]],
        vault_psk: Optional[Dict[str, Any]],
    ) -> None:
        if not vault_psk:
            return
        for device_name, cfg in by_name.items():
            device_vault = vault_psk.get(device_name)
            if not isinstance(device_vault, dict):
                continue
            for if_name, if_cfg in (cfg.get("interfaces") or {}).items():
                if not isinstance(if_cfg, dict):
                    continue
                if_vault = device_vault.get(if_name)
                if not isinstance(if_vault, dict):
                    continue
                for psk in if_cfg.get("presharedKeys") or []:
                    if not isinstance(psk, dict):
                        continue
                    if psk.get("cak"):
                        continue
                    ckn = self._str(psk.get("ckn")).lower()
                    if not ckn:
                        continue
                    cak = self._lookup_vault_cak_by_ckn(if_vault, ckn)
                    if not cak:
                        continue
                    psk["cak"] = cak
                    LOG.debug(
                        "%s Injected CAK for %s interface %s key %s from vault (ckn lookup)",
                        _LOG_PREFIX,
                        device_name,
                        if_name,
                        psk.get("nickname"),
                    )

    @classmethod
    def _validate_psk_secrets_present(
        cls,
        by_name: Dict[str, Dict[str, Any]],
        vault_psk: Optional[Dict[str, Any]] = None,
    ) -> None:
        for device_name, cfg in by_name.items():
            for if_name, if_cfg in (cfg.get("interfaces") or {}).items():
                for psk in if_cfg.get("presharedKeys") or []:
                    if not isinstance(psk, dict):
                        continue
                    state = cls._str(psk.get("state") or "present").lower()
                    if state == "absent":
                        continue
                    nickname = cls._str(psk.get("nickname"))
                    ckn = cls._str(psk.get("ckn")).lower()
                    cak = cls._str(psk.get("cak"))
                    if not ckn:
                        raise ConfigurationError(
                            f"ckn is required for device {device_name!r}, interface {if_name!r}, "
                            f"presharedKeys nickname {nickname!r} when cak is omitted."
                            f"{_CAK_SUPPLY_HINT}"
                        )
                    if not cak:
                        raise ConfigurationError(
                            cls._format_vault_cak_lookup_failure(device_name, if_name, nickname, ckn, vault_psk)
                        )
                    cls._validate_psk_entry(psk, require_secrets=True)

    def apply_macsec(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        vault_devices_macsec_psk: Optional[Dict[str, Any]] = None,
    ) -> dict:
        by_name = self._load_macsec(config_yaml_file, module_params)
        self._inject_vault_psk_secrets(by_name, vault_devices_macsec_psk)
        self._validate_psk_secrets_present(by_name, vault_devices_macsec_psk)
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

            before_all = self._macsec_snapshot_for_device(d)
            edge_payload, after_by_interface = self._build_edge_payload(device_name, cfg, d)
            if not edge_payload:
                LOG.info(
                    "%s No changes needed for %s (ID: %s), skipping",
                    _LOG_PREFIX,
                    device_name,
                    device_id,
                )
                result["skipped_devices"].append(device_name)
                continue

            before_diff = {
                if_name: self._redact_interface_snapshot(before_all.get(if_name) or {})
                for if_name in after_by_interface
            }
            after_diff = {
                if_name: self._redact_interface_snapshot(after) for if_name, after in after_by_interface.items()
            }

            payload = {"edge": edge_payload}
            self._expand_macsec_edge_payload_for_sdk(
                payload["edge"],
                before_all,
                after_by_interface,
            )
            to_push[device_id] = {"device_id": device_id, "payload": payload}
            configured.append(device_name)
            diff_plan.append(
                {
                    "device": device_name,
                    "branch": "edge",
                    "before": before_diff,
                    "after": after_diff,
                }
            )

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

    def get_macsec_status(
        self,
        device_name: str,
        interface_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        enterprise = self.gsdk.enterprise_info["company_name"]
        device_id, _d = fetch_device_by_name(self.gsdk, device_name, enterprise)
        raw = self.gsdk.get_macsec_status(device_id)
        data = sdk_to_dict(raw)
        statuses = data.get("macsecStatuses") or data.get("macsec_statuses") or []
        normalized: List[Dict[str, Any]] = []
        filter_name = self._str(interface_name)
        for item in statuses:
            if not isinstance(item, dict):
                continue
            entry = {
                "interfaceName": self._str(item.get("interfaceName")),
                "status": self._str(item.get("status")),
            }
            if filter_name and entry["interfaceName"] != filter_name:
                continue
            normalized.append(entry)
        return {
            "device": device_name,
            "device_id": device_id,
            "macsec_statuses": normalized,
        }

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        vault_devices_macsec_psk: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_macsec(
            config_yaml_file=config_yaml_file,
            module_params=module_params,
            vault_devices_macsec_psk=vault_devices_macsec_psk,
        )

    def deconfigure(self, config_yaml_file: str) -> dict:
        raise ConfigurationError(
            "Deconfigure is not supported for MACsec. "
            "Use enabled: false to disable MACsec, or presharedKeys state: absent to remove a key."
        )
