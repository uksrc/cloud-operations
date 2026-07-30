"""
NTP Manager for Graphiant Playbooks.

This module manages device-level NTP objects under:
  edge.ntpGlobalObject
- Build raw device-config payload in Python from a structured YAML file
- Idempotency: compare intended NTP objects to current device state; skip push when already matched
- Deconfigure: delete only the objects listed in the YAML by setting config=null per object
"""

from typing import Any, Dict, Iterator, List, Tuple

from .base_manager import BaseManager
from .device_config_common import new_apply_result
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class NtpManager(BaseManager):
    """
    Manage NTP global objects for a given device via raw device-config payload generation.
    """

    @staticmethod
    def _norm_domains(domains: Any) -> List[str]:
        if domains is None:
            return []
        if not isinstance(domains, list):
            raise ConfigurationError("'domains' must be a list of strings")
        out: List[str] = []
        for d in domains:
            if d is None:
                continue
            s = str(d).strip()
            if s:
                out.append(s)
        # Compare order-insensitively; API typically treats it as a set.
        return sorted(out)

    def _payload_differs_from_existing(self, desired_payload: Dict[str, Any], device_info_dict: Any) -> bool:
        desired_edge = (desired_payload or {}).get("edge") or {}
        desired_ntp = desired_edge.get("ntpGlobalObject") or {}
        if not desired_ntp:
            return False

        # Device info may be nested under 'device' or may already be the device dict.
        if isinstance(device_info_dict, dict) and isinstance(device_info_dict.get("device"), dict):
            device_dict = device_info_dict.get("device") or {}
        elif isinstance(device_info_dict, dict):
            device_dict = device_info_dict
        else:
            device_dict = {}

        # The device GET response exposes the effective NTP config as a single object:
        #   device.ntp = { "id": ..., "name": "...", "domains": [...] }
        # Normalize to a map: name -> sorted(domains), matching desired edge.ntpGlobalObject.
        existing_by_name: Dict[str, List[str]] = {}

        existing_ntp_obj = device_dict.get("ntp")
        try:
            if existing_ntp_obj is not None and hasattr(existing_ntp_obj, "to_dict"):
                existing_ntp_dict: Any = existing_ntp_obj.to_dict()
            else:
                existing_ntp_dict = existing_ntp_obj
        except Exception:
            existing_ntp_dict = existing_ntp_obj

        if isinstance(existing_ntp_dict, dict):
            existing_name = existing_ntp_dict.get("name")
            existing_domains = existing_ntp_dict.get("domains")
        else:
            existing_name = getattr(existing_ntp_obj, "name", None)
            existing_domains = getattr(existing_ntp_obj, "domains", None)

        if existing_name:
            existing_by_name[str(existing_name)] = self._norm_domains(existing_domains)

        LOG.debug("[ntp] existing device.ntp map (name->domains): %s", existing_by_name)
        LOG.debug("[ntp] desired edge.ntpGlobalObject: %s", desired_ntp)

        for name, desired_entry in desired_ntp.items():
            if not isinstance(desired_entry, dict):
                return True

            desired_cfg = desired_entry.get("config")
            # Deconfigure semantics: config=null is a no-op if missing.
            if desired_cfg is None:
                if name in existing_by_name:
                    return True
                continue

            if not isinstance(desired_cfg, dict):
                return True

            desired_domains = self._norm_domains(desired_cfg.get("domains"))
            if existing_by_name.get(name) != desired_domains:
                return True

        return False

    def _iter_device_payloads(self, config_yaml_file: str, operation: str) -> Iterator[Tuple[int, str, Dict[str, Any]]]:
        if operation not in ("configure", "deconfigure"):
            raise ConfigurationError(f"Unsupported operation '{operation}'")

        cfg = self.render_config_file(config_yaml_file) or {}
        device_list = cfg.get("ntpGlobalObject") or []
        if not device_list:
            LOG.info("[ntp] No 'ntpGlobalObject' section found in %s", config_yaml_file)
            return

        if not isinstance(device_list, list):
            raise ConfigurationError("'ntpGlobalObject' must be a list of devices")

        for device_entry in device_list:
            if not isinstance(device_entry, dict):
                raise ConfigurationError("Each entry in 'ntpGlobalObject' must be a dict keyed by device name")

            for device_name, device_cfg in device_entry.items():
                if not isinstance(device_cfg, dict):
                    raise ConfigurationError(f"Device '{device_name}' config must be a dict")

                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise DeviceNotFoundError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. Please check device name."
                    )

                ntp_cfg = device_cfg.get("ntps")
                # Build per-device ntpGlobalObject payload (inline)
                items: List[Dict[str, Any]]
                if ntp_cfg is None:
                    items = []
                elif isinstance(ntp_cfg, list):
                    items = []
                    for entry in ntp_cfg:
                        if isinstance(entry, str):
                            items.append({"name": entry})
                        elif isinstance(entry, dict):
                            items.append(entry)
                        else:
                            raise ConfigurationError("Each NTP entry must be a dict or string name")
                elif isinstance(ntp_cfg, dict):
                    # Allow dict keyed by name -> {domains:[...]}
                    items = []
                    for name, cfg_item in ntp_cfg.items():
                        if cfg_item is None:
                            cfg_item = {}
                        if not isinstance(cfg_item, dict):
                            raise ConfigurationError("'ntps' dict values must be dicts")
                        merged = {"name": name}
                        merged.update(cfg_item)
                        items.append(merged)
                else:
                    raise ConfigurationError("'ntps' must be a list or dict")

                ntp_payload: Dict[str, Any] = {}
                for item in items:
                    if not isinstance(item, dict):
                        raise ConfigurationError("Each NTP object must be a dict")
                    name = item.get("name")
                    if not name:
                        raise ConfigurationError("NTP object missing 'name'")
                    if operation == "deconfigure":
                        ntp_payload[name] = {"config": None}
                    else:
                        domains = NtpManager._norm_domains(item.get("domains"))
                        ntp_payload[name] = {"config": {"name": name, "domains": domains}}
                payload: Dict[str, Any] = {"edge": {"ntpGlobalObject": ntp_payload}}
                yield device_id, device_name, payload

    def _ntp_snapshot_from_device(self, device_info_dict: Any) -> Dict[str, Any]:
        if isinstance(device_info_dict, dict) and isinstance(device_info_dict.get("device"), dict):
            device_dict = device_info_dict.get("device") or {}
        elif isinstance(device_info_dict, dict):
            device_dict = device_info_dict
        else:
            device_dict = {}
        existing_ntp_obj = device_dict.get("ntp")
        try:
            existing_ntp_dict: Any = (
                existing_ntp_obj.to_dict()
                if existing_ntp_obj is not None and hasattr(existing_ntp_obj, "to_dict")
                else existing_ntp_obj
            )
        except Exception:
            existing_ntp_dict = existing_ntp_obj
        if isinstance(existing_ntp_dict, dict):
            name = existing_ntp_dict.get("name")
            domains = existing_ntp_dict.get("domains")
            if name:
                return {str(name): {"config": {"name": str(name), "domains": self._norm_domains(domains)}}}
        return {}

    def apply_ntp(self, config_yaml_file: str, operation: str) -> dict:
        result = new_apply_result()
        output_config: Dict[int, Dict[str, Any]] = {}

        for device_id, device_name, payload in self._iter_device_payloads(config_yaml_file, operation=operation):
            gcs_device_info = self.gsdk.get_device_info(device_id)
            if gcs_device_info is None:
                raise ConfigurationError(f"Failed to retrieve device info for device_id={device_id}")

            try:
                device_info_dict = gcs_device_info.to_dict()
            except Exception:
                device_info_dict = gcs_device_info

            if not self._payload_differs_from_existing(payload, device_info_dict):
                LOG.info("[ntp] ✓ No changes needed for %s (ID: %s), skipping", device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            before = self._ntp_snapshot_from_device(device_info_dict)
            after = dict(payload.get("edge", {}).get("ntpGlobalObject") or {})
            result["diff_plan"].append(
                {"device": device_name, "branch": "edge.ntpGlobalObject", "before": before, "after": after}
            )

            output_config[device_id] = {"device_id": device_id, "payload": payload}
            result["configured_devices"].append(device_name)

        if not output_config:
            return result

        LOG.info("[ntp] Pushing payload for %d device(s)...", len(output_config))
        self.execute_concurrent_tasks(self.gsdk.put_device_config_raw, output_config)

        result["changed"] = True
        return result

    def configure(self, config_yaml_file: str) -> dict:
        return self.apply_ntp(config_yaml_file, operation="configure")

    def deconfigure(self, config_yaml_file: str) -> dict:
        return self.apply_ntp(config_yaml_file, operation="deconfigure")
