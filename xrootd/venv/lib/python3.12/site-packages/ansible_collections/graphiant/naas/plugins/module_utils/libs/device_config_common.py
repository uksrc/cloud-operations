"""
Shared helpers for device ``PUT /v1/devices/{id}/config`` managers.

Used by ``device_system_manager``, ``edge_services_manager``, ``traffic_policy_manager``, and intended for future
managers (e.g. ``ntp_manager``, ``static_routes_manager``) that need idempotency,
``diff_plan``, check mode, and the list-of-single-key-dicts YAML pattern.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import ConfigurationError, DeviceNotFoundError
from .logger import setup_logger

LOG = setup_logger()

# API payload keys redacted in library log output (non-Ansible paths).
# Add names here for new secret fields; see CREDENTIAL_MANAGEMENT_GUIDE.md.
_SENSITIVE_LOG_KEYS = frozenset(
    {
        "localWebServerPassword",
        "presharedKey",
        "psk",
        "cak",
        "md5Password",
    }
)


def redact_sensitive_for_log(value: Any) -> Any:
    """
    Return a deep copy of ``value`` with known secret field names replaced for logging.

    Redaction is by JSON key name (Graphiant API / config fields), not by vault values.
    Does not modify the original object; safe to use on ``to_dict()`` output before ``LOG.info``.
    """
    if isinstance(value, dict):
        return {
            key: ("********" if key in _SENSITIVE_LOG_KEYS else redact_sensitive_for_log(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_for_log(item) for item in value]
    return value


def format_config_payload_for_log(payload: Any) -> str:
    """Format a config payload dict for ``LOG.info`` without logging secret values."""
    return json.dumps(redact_sensitive_for_log(payload), indent=2)


def coerce_str(val: Any) -> str:
    """Normalize optional scalars to a stripped string (empty when None)."""
    return "" if val is None else str(val).strip()


def sdk_to_dict(obj: Any) -> Dict[str, Any]:
    """Coerce SDK model or mapping to ``dict``."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            d = obj.to_dict()
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def unwrap_device(root: Dict[str, Any]) -> Dict[str, Any]:
    """Return inner ``device`` dict from GET response when present."""
    inner = root.get("device")
    return inner if isinstance(inner, dict) else root


def as_dict(block: Any) -> Dict[str, Any]:
    """Alias for ``sdk_to_dict`` (nested config blocks)."""
    return sdk_to_dict(block)


def device_not_found_message(device_name: str, enterprise_name: str) -> str:
    return (
        f"Device '{device_name}' is not found in the current enterprise: "
        f"{enterprise_name}. Please check device name."
    )


def fetch_device_by_name(gsdk: Any, device_name: str, enterprise_name: str) -> Tuple[int, Dict[str, Any]]:
    """
    Resolve portal hostname to device id and normalized GET ``device`` dict.

    Raises:
        DeviceNotFoundError: Unknown device name.
        ConfigurationError: GET failed.
    """
    device_id = gsdk.get_device_id(device_name)
    if device_id is None:
        raise DeviceNotFoundError(device_not_found_message(device_name, enterprise_name))

    gcs = gsdk.get_device_info(device_id)
    if gcs is None:
        raise ConfigurationError(f"Failed to retrieve device info for device_id={device_id}")

    info_dict = gcs.to_dict() if hasattr(gcs, "to_dict") else gcs
    device_dict = unwrap_device(sdk_to_dict(info_dict))
    return device_id, device_dict


def merge_dict_override(merged: Dict[str, Any], ov: Dict[str, Any]) -> Dict[str, Any]:
    """Default module-param override: shallow merge onto the YAML row."""
    merged.update(ov)
    return merged


def load_device_list_yaml_config(
    yaml_key: str,
    config_yaml_file: Optional[str],
    module_params: Optional[Dict[str, Any]],
    render_config_file: Callable[[str], Dict[str, Any]],
    *,
    missing_input_error: str,
    build_row_from_params: Callable[[Dict[str, Any]], Dict[str, Any]],
    validate_device_cfg: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    merge_override: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Load ``{yaml_key: [{device_name: settings}, ...]}`` plus optional module-param overrides.

    Same structural pattern as ``device_system`` / ``edge_services`` YAML files.
    """
    path = coerce_str(config_yaml_file) or None
    cfg = render_config_file(path) or {} if path else {}

    raw = cfg.get(yaml_key)
    by_name: Dict[str, Dict[str, Any]] = {}
    if raw is None:
        pass
    elif not isinstance(raw, list):
        raise ConfigurationError(f"'{yaml_key}' must be a list of device entries")
    else:
        for entry in raw:
            if not isinstance(entry, dict) or not entry:
                raise ConfigurationError(
                    f"Each entry in '{yaml_key}' must be a non-empty dict keyed by portal device name"
                )
            for dev, c in entry.items():
                by_name[dev] = c if isinstance(c, dict) else {}

    mp = module_params or {}
    portal = coerce_str(mp.get("device"))
    if not path and not portal:
        raise ConfigurationError(missing_input_error)

    if not path:
        by_name[portal] = build_row_from_params(mp)

    merge = merge_override or merge_dict_override
    target = coerce_str(mp.get("device"))
    override_row = build_row_from_params(mp)
    if target and override_row:
        if target in by_name:
            by_name[target] = merge(dict(by_name[target]), override_row)
        else:
            by_name[target] = dict(override_row)

    return {name: validate_device_cfg(name, c) for name, c in by_name.items()}


def new_apply_result(**extra: Any) -> Dict[str, Any]:
    """Standard manager result skeleton (``diff_plan``, device lists, ``changed``)."""
    result: Dict[str, Any] = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
        "diff_plan": [],
    }
    result.update(extra)
    return result


def push_device_config_raw(
    execute_concurrent_tasks: Callable[..., Any],
    put_fn: Callable[..., Any],
    to_push: Dict[int, Dict[str, Any]],
    *,
    log_prefix: str,
) -> None:
    """Run ``put_device_config_raw`` (or compatible) for all pending device payloads."""
    if not to_push:
        return
    LOG.info("%s Pushing payload for %d device(s)...", log_prefix, len(to_push))
    execute_concurrent_tasks(put_fn, to_push)


def ansible_diff_from_plan(diff_plan: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build Ansible ``diff`` dict (string before/after) from manager ``diff_plan``."""
    before_chunks: List[str] = []
    after_chunks: List[str] = []
    for item in diff_plan:
        dev = item.get("device", "")
        branch = item.get("branch", "")
        header = f"=== {dev} ({branch}) ===\n"
        before_chunks.append(header + json.dumps(item.get("before") or {}, sort_keys=True, indent=2))
        after_chunks.append(header + json.dumps(item.get("after") or {}, sort_keys=True, indent=2))
    return {"before": "\n\n".join(before_chunks) + "\n", "after": "\n\n".join(after_chunks) + "\n"}


def apply_module_diff(module: Any, exit_payload: Dict[str, Any], details: Dict[str, Any]) -> None:
    """Populate ``diff`` in *exit_payload* when the playbook is run with ``--diff``.

    Call this just before ``module.exit_json(**exit_payload)`` in every module that
    supports diff mode.  *details* is the manager result dict (contains ``diff_plan``).
    """
    diff_plan = (details or {}).get("diff_plan") or []
    if getattr(module, "_diff", False) and diff_plan:
        exit_payload["diff"] = ansible_diff_from_plan(diff_plan)


def dtype_from_device_role(role: Any) -> Optional[str]:
    """Map portal ``role`` to config branch name (``edge`` or ``core``)."""
    r = coerce_str(role).lower()
    if r == "core":
        return "core"
    if r == "cpe":
        return "edge"
    return None


def normalized_device_type(raw: Any) -> Optional[str]:
    """Return ``edge`` or ``core`` when set; ``None`` when absent."""
    if raw is None or coerce_str(raw) == "":
        return None
    dt = coerce_str(raw).lower()
    if dt not in ("edge", "core"):
        raise ConfigurationError("'device_type' must be 'edge' or 'core'.")
    return dt
