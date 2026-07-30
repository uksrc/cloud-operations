"""
Traffic Policy Manager for Graphiant Playbooks.

Manages device-level traffic policy objects under:
  edge.trafficPolicy.trafficRulesets
- Build raw device-config payload in Python from a structured YAML file
- Idempotency: compare intended rulesets to current device state; skip push when already matched
- Check mode: read device state, skip writes, accurate ``changed``; ``diff_plan`` for ``--diff`` (per-rule)
- Deconfigure: delete only the rulesets listed in the YAML by setting ruleset=null per key
- Per-object state in YAML: ruleset or rule ``state: absent`` sends ``ruleset: null`` or ``rule: null``
  under ``configure`` (same idea as static route ``route: null`` deconfigure entries)

LAN segment association (per-segment ruleset reference):
  edge.segments.<segment>.trafficRuleset.ruleset -> ruleset name (string)
- attach_to_lan_segments / detach_from_lan_segments with optional ``segments`` in YAML
- Configure workflow: ``configure`` (rulesets) then ``attach_to_lan_segments`` (segments)
- Deconfigure workflow: ``detach_from_lan_segments`` (segments) then ``deconfigure`` (rulesets)
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_manager import BaseManager
from .device_config_common import (
    as_dict,
    fetch_device_by_name,
    load_device_list_yaml_config,
    new_apply_result,
    push_device_config_raw,
    unwrap_device,
)
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()

TRAFFIC_POLICY_KEYS = ("trafficPolicy", "traffic_policy")
TRAFFIC_RULESETS_KEYS = ("trafficRulesets", "traffic_rulesets")
SEGMENT_NAME_KEYS = (
    "name",
    "lanSegment",
    "lan_segment",
    "segmentName",
    "segment_name",
    "segment",
    "vrfName",
    "vrf",
)
TRAFFIC_RULESET_KEYS = ("trafficRuleset", "traffic_ruleset")
RULESET_REF_KEYS = ("ruleset", "name", "rulesetName", "ruleset_name", "id")
WRAPPER_KEYS = ("match", "val")
FIELD_ALIASES = {
    "match": ("val",),
    "codePoint": (
        "code_point",
        "value",
        "dscpCodePoint",
        "dscp_code_point",
        "remarkCodePoint",
        "remark_code_point",
    ),
    "setSlaClass": ("slaClass", "sla_class", "set_sla_class"),
    "primaryCircuitLabel": ("primary_circuit_label",),
    "backupCircuitLabel": ("backup_circuit_label",),
    "dscp": ("dscpCodePoint", "dscp_code_point"),
    "remark": ("remarkCodePoint", "remark_code_point"),
    "destinationNetwork": ("destination_network",),
    "sourceNetwork": ("source_network",),
    "ipProtocol": ("ip_protocol", "protocol"),
    "icmpType": ("icmp_type",),
}
OMITTED_DEFAULTS = {
    "icmpType": 0,
    "logging": False,
}
_STATE_CHOICES = frozenset({"present", "absent"})
_LOG_PREFIX = "[traffic-policy]"
_YAML_KEY = "trafficPolicyObject"


class TrafficPolicyManager(BaseManager):
    """
    Manage traffic policy rulesets and LAN-segment ruleset references via raw device-config payloads.
    """

    @classmethod
    def _device_dict(cls, device_info_dict: Any) -> Dict[str, Any]:
        return unwrap_device(as_dict(device_info_dict))

    @staticmethod
    def _validate_device_cfg(device_name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        return cfg

    def _load_devices(self, config_yaml_file: str) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            None,
            self.render_config_file,
            missing_input_error="traffic_policy_config_file is required.",
            build_row_from_params=lambda _mp: {},
            validate_device_cfg=self._validate_device_cfg,
        )

    @staticmethod
    def _first_present(mapping: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            if key in mapping:
                return mapping.get(key)
        return None

    @staticmethod
    def _existing_value_for_key(mapping: Dict[str, Any], key: str) -> Tuple[bool, Any]:
        if not isinstance(mapping, dict):
            return False, None
        if key in mapping:
            return True, mapping.get(key)
        for alias in FIELD_ALIASES.get(key, ()):
            if alias in mapping:
                return True, mapping.get(alias)
        return False, None

    @staticmethod
    def _matches_omitted_default(key: str, desired_value: Any, existing_value: Any = None) -> bool:
        if key not in OMITTED_DEFAULTS:
            return False
        return desired_value == OMITTED_DEFAULTS[key] and existing_value is None

    @classmethod
    def _normalize(cls, obj: Any) -> Any:
        """Stable JSON-comparable structure for diffing (dict key order normalized)."""
        if obj is None:
            return None
        if hasattr(obj, "to_dict"):
            try:
                return cls._normalize(obj.to_dict())
            except Exception:  # nosec B110 — to_dict() fallback; failure is non-fatal, obj normalised as-is
                pass
        if isinstance(obj, dict):
            return {str(k): cls._normalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
        if isinstance(obj, list):
            return [cls._normalize(v) for v in obj]
        if isinstance(obj, (str, int, float, bool)):
            return obj
        return str(obj)

    @classmethod
    def _is_effectively_null(cls, obj: Any) -> bool:
        if obj is None:
            return True
        if isinstance(obj, dict):
            return all(cls._is_effectively_null(v) for v in obj.values())
        return False

    @classmethod
    def _single_leaf_value(cls, obj: Any) -> Tuple[bool, Any]:
        if not isinstance(obj, dict):
            return True, obj
        if len(obj) != 1:
            return False, None
        value = next(iter(obj.values()))
        return cls._single_leaf_value(value)

    @classmethod
    def _desired_matches_existing(cls, desired: Any, existing: Any) -> bool:
        """
        Compare desired config as a subset of existing device state.

        The API may add defaults or omit null-valued fields. Idempotency should only
        fail when a field explicitly set by the YAML differs in current state.
        """
        if isinstance(desired, dict):
            if not isinstance(existing, dict):
                if cls._is_effectively_null(desired) and existing is None:
                    return True
                has_single_leaf, leaf_value = cls._single_leaf_value(desired)
                return has_single_leaf and cls._normalize(leaf_value) == cls._normalize(existing)
            for key, desired_value in desired.items():
                found, existing_value = cls._existing_value_for_key(existing, key)
                if not found:
                    if key in WRAPPER_KEYS and cls._desired_matches_existing(desired_value, existing):
                        continue
                    if cls._matches_omitted_default(key, desired_value):
                        continue
                    if cls._is_effectively_null(desired_value):
                        continue
                    return False
                if cls._matches_omitted_default(key, desired_value, existing_value):
                    continue
                if not cls._desired_matches_existing(desired_value, existing_value):
                    return False
            return True

        if isinstance(desired, list):
            return cls._normalize(desired) == cls._normalize(existing)

        return cls._normalize(desired) == cls._normalize(existing)

    @classmethod
    def _first_mismatch_path(cls, desired: Any, existing: Any, path: str = "") -> Optional[str]:
        if isinstance(desired, dict):
            if not isinstance(existing, dict):
                if cls._is_effectively_null(desired) and existing is None:
                    return None
                has_single_leaf, leaf_value = cls._single_leaf_value(desired)
                if has_single_leaf and cls._normalize(leaf_value) == cls._normalize(existing):
                    return None
                return path or "<root>"
            for key, desired_value in desired.items():
                child_path = f"{path}.{key}" if path else str(key)
                found, existing_value = cls._existing_value_for_key(existing, key)
                if not found:
                    if key in WRAPPER_KEYS and cls._desired_matches_existing(desired_value, existing):
                        continue
                    if cls._matches_omitted_default(key, desired_value):
                        continue
                    if cls._is_effectively_null(desired_value):
                        continue
                    return child_path
                if cls._matches_omitted_default(key, desired_value, existing_value):
                    continue
                mismatch = cls._first_mismatch_path(desired_value, existing_value, child_path)
                if mismatch:
                    return mismatch
            return None

        if isinstance(desired, list):
            return None if cls._normalize(desired) == cls._normalize(existing) else path or "<root>"

        return None if cls._normalize(desired) == cls._normalize(existing) else path or "<root>"

    @staticmethod
    def _value_at_path(obj: Any, path: Optional[str]) -> Any:
        if not path or path == "<root>":
            return obj
        cur = obj
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    @staticmethod
    def _parent_path(path: Optional[str]) -> Optional[str]:
        if not path or path == "<root>" or "." not in path:
            return None
        return path.rsplit(".", 1)[0]

    def _extract_rulesets_from_device(self, device_info_dict: Any) -> Dict[str, Any]:
        d = self._device_dict(device_info_dict)
        edge = as_dict(d.get("edge"))
        for container in (edge, d):
            tp_source = self._first_present(container, TRAFFIC_POLICY_KEYS)
            tp = as_dict(tp_source)
            rs = self._first_present(tp, TRAFFIC_RULESETS_KEYS)
            if rs is not None:
                return self._coerce_rulesets_map(rs)
        return {}

    @staticmethod
    def _ruleset_name_from_entry(entry: Any) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        ruleset_body = entry.get("ruleset")
        if isinstance(ruleset_body, dict):
            ruleset: Dict[str, Any] = ruleset_body
        else:
            ruleset = entry
        name = TrafficPolicyManager._first_present(ruleset, RULESET_REF_KEYS) or entry.get("name")
        return str(name).strip() if name else None

    @staticmethod
    def _coerce_rulesets_map(rulesets: Any) -> Dict[str, Any]:
        if not rulesets:
            return {}

        if isinstance(rulesets, dict):
            mapped: Dict[str, Any] = dict(rulesets)
            for key, entry in rulesets.items():
                name = TrafficPolicyManager._ruleset_name_from_entry(entry)
                if name:
                    mapped.setdefault(name, entry)
                elif isinstance(key, str):
                    mapped.setdefault(key.strip(), entry)
            return mapped

        if isinstance(rulesets, list):
            out: Dict[str, Any] = {}
            for item in rulesets:
                if not isinstance(item, dict):
                    continue
                name = TrafficPolicyManager._ruleset_name_from_entry(item)
                if name:
                    out[str(name).strip()] = item
            return out

        return {}

    @staticmethod
    def _existing_ruleset_from_entry(existing_entry: Any) -> Any:
        if not isinstance(existing_entry, dict):
            return None
        if "ruleset" in existing_entry:
            return existing_entry.get("ruleset")
        if any(k in existing_entry for k in ("name", "rules", "description")):
            return existing_entry
        return None

    @classmethod
    def _coerce_existing_rules_map(cls, rules: Any) -> Any:
        if isinstance(rules, dict):
            return rules
        if not isinstance(rules, list):
            return rules

        out: Dict[str, Any] = {}
        for item in rules:
            if not isinstance(item, dict):
                continue
            rule_obj = item.get("rule") if isinstance(item.get("rule"), dict) else item
            seq = rule_obj.get("seq") if isinstance(rule_obj, dict) else None
            if seq is None:
                continue
            out[str(seq).strip()] = item if "rule" in item else {"rule": rule_obj}
        return out

    @classmethod
    def _coerce_existing_ruleset_body(cls, ruleset: Any, ruleset_name: str) -> Any:
        if not isinstance(ruleset, dict):
            return ruleset

        out = dict(ruleset)
        # Some API responses use the map key as the ruleset identity and omit
        # the nested name field. The YAML always includes it after normalization.
        out.setdefault("name", ruleset_name)
        if "rules" in out:
            out["rules"] = cls._coerce_existing_rules_map(out.get("rules"))
        return out

    @classmethod
    def _normalized_state(cls, value: Any, *, context: str) -> str:
        if value is None:
            return "present"
        state = str(value).strip().lower()
        if state not in _STATE_CHOICES:
            raise ConfigurationError(f"{context}: 'state' must be 'present' or 'absent'")
        return state

    @classmethod
    def _rule_delete_entry(cls) -> Dict[str, Any]:
        return {"rule": None}

    @classmethod
    def _rule_state_from_shapes(cls, entry: Dict[str, Any], rule_obj: Dict[str, Any], *, context: str) -> str:
        state = entry.get("state")
        if state is None:
            state = rule_obj.get("state")
        return cls._normalized_state(state, context=context)

    @staticmethod
    def _strip_rule_state(entry: Dict[str, Any], rule_obj: Dict[str, Any]) -> Dict[str, Any]:
        cleaned_entry = dict(entry)
        cleaned_rule = dict(rule_obj)
        cleaned_entry.pop("state", None)
        cleaned_rule.pop("state", None)
        if "rule" in cleaned_entry:
            cleaned_entry["rule"] = cleaned_rule
            return cleaned_entry
        return cleaned_rule

    @classmethod
    def _rules_from_yaml(cls, rules_cfg: Any) -> Dict[str, Any]:
        """
        Build the API rules map.

        YAML may either use the raw API map shape:
          "10": { rule: { seq: 10, ... } }

        or the simpler list shape:
          - seq: 10
            match: ...
            action: ...

        Per-rule lifecycle (under ``configure``):
          - seq: 500
            state: absent

        sends ``{"500": {"rule": null}}`` (delete that rule only).
        """
        if rules_cfg is None:
            return {}

        if isinstance(rules_cfg, dict):
            out: Dict[str, Any] = {}
            for raw_key, raw_val in rules_cfg.items():
                key = str(raw_key).strip()
                if not key:
                    raise ConfigurationError("rules dict keys must be non-empty sequence numbers")
                if not isinstance(raw_val, dict):
                    raise ConfigurationError(f"rules['{key}'] must be a dict")
                entry = dict(raw_val)
                if entry.get("rule") is None and "rule" in entry:
                    out[key] = cls._rule_delete_entry()
                    continue
                rule_obj = entry.get("rule") if "rule" in entry else entry
                if not isinstance(rule_obj, dict):
                    raise ConfigurationError(f"rules['{key}'] must be a dict")
                state = cls._rule_state_from_shapes(entry, rule_obj, context=f"rule {key}")
                if state == "absent":
                    out[key] = cls._rule_delete_entry()
                    continue
                cleaned = cls._strip_rule_state(entry, rule_obj)
                if isinstance(cleaned, dict) and "rule" in cleaned:
                    cleaned["rule"] = cls._normalize_rule_body(cleaned.get("rule"))
                    out[key] = cleaned
                else:
                    out[key] = {"rule": cls._normalize_rule_body(cleaned)}
            return out

        if isinstance(rules_cfg, list):
            out = {}
            for entry in rules_cfg:
                if not isinstance(entry, dict):
                    raise ConfigurationError("rules list items must be dicts")
                entry_copy = dict(entry)
                rule_obj = entry_copy.get("rule") if "rule" in entry_copy else dict(entry_copy)
                if not isinstance(rule_obj, dict):
                    raise ConfigurationError("rules list item 'rule' must be a dict")
                rule_obj = dict(rule_obj)
                seq = rule_obj.get("seq")
                if seq is None:
                    raise ConfigurationError("rules list item missing 'seq'")
                key = str(seq).strip()
                if not key:
                    raise ConfigurationError("rules list item 'seq' must be non-empty")
                state = cls._rule_state_from_shapes(entry_copy, rule_obj, context=f"rule seq {key}")
                if state == "absent":
                    out[key] = cls._rule_delete_entry()
                    continue
                cleaned = cls._strip_rule_state(entry_copy, rule_obj)
                if isinstance(cleaned, dict) and "rule" in cleaned:
                    cleaned["rule"] = cls._normalize_rule_body(cleaned.get("rule"))
                    out[key] = cleaned
                else:
                    out[key] = {"rule": cls._normalize_rule_body(cleaned)}
            return out

        raise ConfigurationError("'rules' must be a dict or list")

    @staticmethod
    def _normalize_circuit_label(value: Any, field_name: str) -> Any:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, str):
            label = value.strip()
            if not label:
                raise ConfigurationError(f"'{field_name}' label must be non-empty")
            return {"label": label}
        raise ConfigurationError(f"'{field_name}' must be a string label or dict")

    @staticmethod
    def _set_nested(target: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
        cur = target
        for key in path[:-1]:
            nxt = cur.get(key)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[key] = nxt
            cur = nxt
        cur[path[-1]] = value

    @classmethod
    def _match_from_shorthand(cls, rule: Dict[str, Any]) -> Dict[str, Any]:
        match = dict(rule.get("match") or {})

        app_builtin = rule.pop("applicationBuiltin", None)
        if app_builtin is not None:
            cls._set_nested(match, ("application", "match", "builtin"), app_builtin)

        app_custom = rule.pop("applicationCustom", None)
        if app_custom is not None:
            cls._set_nested(match, ("application", "match", "custom"), app_custom)

        for field_name in ("ipProtocol", "sourcePort", "destinationPort", "icmpType"):
            if field_name in rule:
                match[field_name] = rule.pop(field_name)

        for field_name in ("sourceNetwork", "destinationNetwork"):
            if field_name in rule:
                value = rule.pop(field_name)
                match[field_name] = value if isinstance(value, dict) else {field_name: value}

        dscp_code_point = rule.pop("dscpCodePoint", None)
        if dscp_code_point is not None:
            cls._set_nested(match, ("dscp", "match", "codePoint"), dscp_code_point)

        return match

    @classmethod
    def _action_from_shorthand(cls, rule: Dict[str, Any]) -> Dict[str, Any]:
        action = dict(rule.get("action") or {})

        for field_name in ("logging", "egress", "primaryCircuitLabel", "backupCircuitLabel"):
            if field_name in rule:
                action[field_name] = rule.pop(field_name)

        sla_class = rule.pop("slaClass", None)
        if sla_class is not None:
            action["setSlaClass"] = {"class": sla_class}

        remark_code_point = rule.pop("remarkCodePoint", None)
        if remark_code_point is not None:
            action["remark"] = {"val": {"codePoint": remark_code_point}}

        for field_name in ("primaryCircuitLabel", "backupCircuitLabel"):
            if field_name in action:
                action[field_name] = cls._normalize_circuit_label(action.get(field_name), field_name)

        if "primaryCircuitLabel" in action and "backupCircuitLabel" not in action:
            action["backupCircuitLabel"] = {"label": None}

        return action

    @staticmethod
    def _normalize_rule_body(rule: Any) -> Any:
        if not isinstance(rule, dict):
            return rule

        out = dict(rule)
        match = TrafficPolicyManager._match_from_shorthand(out)
        if match:
            out["match"] = match

        action = TrafficPolicyManager._action_from_shorthand(out)
        if action:
            out["action"] = action
        return out

    def _normalize_ruleset_body(self, ruleset: Any) -> Any:
        if not isinstance(ruleset, dict):
            return ruleset
        out = dict(ruleset)
        if "rules" in out:
            out["rules"] = self._rules_from_yaml(out.get("rules"))
        return out

    def _normalize_ruleset_entry(self, key: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(entry)
        ruleset = out.get("ruleset")
        if ruleset is not None:
            if not isinstance(ruleset, dict):
                raise ConfigurationError(f"trafficRulesets['{key}'].ruleset must be a dict or null")
            normalized = self._normalize_ruleset_body(ruleset)
            if isinstance(normalized, dict) and not normalized.get("name"):
                normalized["name"] = key
            out["ruleset"] = normalized
        return out

    def _rulesets_from_yaml(self, tr_cfg: Any, operation: str) -> Dict[str, Any]:
        """
        Build the trafficRulesets map for the device-config API.

        Supported YAML shapes:
        - dict keyed by ruleset id -> either ``{ruleset: {...}}`` or the inner ruleset body only
        - list of dicts with ``name`` (configure) or list of strings / ``{name: ...}`` (deconfigure)
        """
        if tr_cfg is None:
            return {}
        if isinstance(tr_cfg, dict):
            out: Dict[str, Any] = {}
            for raw_key, v in tr_cfg.items():
                key = str(raw_key).strip()
                if not key:
                    raise ConfigurationError("trafficRulesets dict keys must be non-empty strings")
                if operation == "deconfigure":
                    out[key] = {"ruleset": None}
                    continue
                if not isinstance(v, dict):
                    raise ConfigurationError(f"trafficRulesets['{key}'] must be a dict")
                v = dict(v)
                rs_state = self._normalized_state(v.pop("state", None), context=f"ruleset '{key}'")
                if rs_state == "absent":
                    out[key] = {"ruleset": None}
                    continue
                if "ruleset" in v:
                    out[key] = self._normalize_ruleset_entry(key, v)
                else:
                    out[key] = self._normalize_ruleset_entry(key, {"ruleset": v})
            return out
        if isinstance(tr_cfg, list):
            out = {}
            for entry in tr_cfg:
                if operation == "deconfigure":
                    if isinstance(entry, str):
                        k = str(entry).strip()
                        if not k:
                            continue
                        out[k] = {"ruleset": None}
                    elif isinstance(entry, dict):
                        n = entry.get("name")
                        if not n:
                            raise ConfigurationError("trafficRulesets list entry missing 'name' for deconfigure")
                        out[str(n).strip()] = {"ruleset": None}
                    else:
                        raise ConfigurationError("trafficRulesets list entries must be str or dict for deconfigure")
                    continue
                if not isinstance(entry, dict):
                    raise ConfigurationError("trafficRulesets list items must be dicts with a 'name' field")
                n = entry.get("name")
                if not n:
                    raise ConfigurationError("trafficRulesets list entry missing 'name'")
                name = str(n).strip()
                rs_state = self._normalized_state(entry.get("state"), context=f"ruleset '{name}'")
                if rs_state == "absent":
                    out[name] = {"ruleset": None}
                    continue
                body = {k: val for k, val in entry.items() if k not in ("name", "state")}
                out[name] = {"ruleset": self._normalize_ruleset_body({"name": name, **body})}
            return out
        raise ConfigurationError("'trafficRulesets' must be a dict or list")

    @staticmethod
    def _matches_named_object(obj: Any, name: str) -> bool:
        return isinstance(obj, dict) and TrafficPolicyManager._first_present(obj, SEGMENT_NAME_KEYS) == name

    @staticmethod
    def _find_segment_object(device_dict: Dict[str, Any], seg_name: str) -> Optional[Dict[str, Any]]:
        """Resolve a LAN segment by name from a device GET dict (same heuristics as static routes)."""
        if not isinstance(device_dict, dict):
            return None

        edge = device_dict.get("edge") or {}
        segments = None
        if isinstance(edge, dict):
            for key in ("segments", "lanSegments", "lan_segments", "vrfs", "vrFs"):
                if key in edge:
                    segments = edge.get(key)
                    break
        if segments is None:
            for key in ("segments", "lanSegments", "lan_segments", "vrfs", "vrFs"):
                if key in device_dict:
                    segments = device_dict.get(key)
                    break

        seg_obj: Any = None
        if isinstance(segments, dict):
            seg_obj = segments.get(seg_name)
            if seg_obj is None:
                for seg_value in segments.values():
                    if TrafficPolicyManager._matches_named_object(seg_value, seg_name):
                        seg_obj = seg_value
                        break
        elif isinstance(segments, list):
            for item in segments:
                if TrafficPolicyManager._matches_named_object(item, seg_name):
                    seg_obj = item
                    break

        return seg_obj if isinstance(seg_obj, dict) else None

    @classmethod
    def _coerce_ruleset_ref(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            ref = cls._first_present(value, RULESET_REF_KEYS)
            if ref is None:
                return None
            return cls._coerce_ruleset_ref(ref)
        ref = str(value).strip()
        return None if not ref or ref.lower() in ("none", "null") else ref

    @classmethod
    def _traffic_ruleset_ref_from_segment(cls, seg_obj: Optional[Dict[str, Any]]) -> Optional[str]:
        if not seg_obj:
            return None
        tr = cls._first_present(seg_obj, TRAFFIC_RULESET_KEYS)
        direct_ref = cls._coerce_ruleset_ref(tr)
        if direct_ref is not None or tr is not None:
            return direct_ref
        for value in seg_obj.values():
            if isinstance(value, dict):
                nested_ref = cls._traffic_ruleset_ref_from_segment(value)
                if nested_ref is not None:
                    return nested_ref
        return None

    @staticmethod
    def _ruleset_refs_match(desired_ref: Any, existing_ref: Optional[str]) -> bool:
        desired = str(desired_ref).strip()
        existing = (existing_ref or "").strip()
        if desired == existing:
            return True
        # The API may return generated names like G-<device-id>-<ruleset-name>.
        return bool(desired and existing.endswith(f"-{desired}"))

    def _segments_payload_from_yaml(self, segments_cfg: Any, operation: str) -> Dict[str, Any]:
        """
        Build edge.segments map: each value is ``{ trafficRuleset: { ruleset: "<name>" } }``.

        YAML may use API shape or shorthand ``segment_name: ruleset_name`` (string value).
        """
        if segments_cfg is None:
            return {}
        if not isinstance(segments_cfg, dict):
            raise ConfigurationError("'segments' must be a dict keyed by LAN segment name")

        out: Dict[str, Any] = {}
        for raw_seg, raw_val in segments_cfg.items():
            seg = str(raw_seg).strip()
            if not seg:
                raise ConfigurationError("segments dict keys must be non-empty segment names")

            if operation == "detach_from_lan_segments":
                out[seg] = {"trafficRuleset": {"ruleset": None}}
                continue

            if isinstance(raw_val, str):
                name = raw_val.strip()
                if not name:
                    raise ConfigurationError(f"segments['{seg}']: ruleset name must be non-empty")
                out[seg] = {"trafficRuleset": {"ruleset": name}}
            elif isinstance(raw_val, dict):
                if "trafficRuleset" in raw_val:
                    out[seg] = raw_val
                elif "ruleset" in raw_val:
                    out[seg] = {"trafficRuleset": raw_val}
                else:
                    raise ConfigurationError(
                        f"segments['{seg}']: expected string ruleset name, "
                        f"or dict with 'trafficRuleset' / 'ruleset' keys"
                    )
            else:
                raise ConfigurationError(f"segments['{seg}']: value must be a string or dict")

        return out

    def _payload_differs(self, desired_payload: Dict[str, Any], device_info_dict: Any) -> bool:
        desired_edge = (desired_payload or {}).get("edge") or {}
        desired_segments = desired_edge.get("segments") or {}
        if isinstance(desired_segments, dict) and desired_segments:
            return self._segment_attachments_need_update(desired_segments, device_info_dict)

        desired_tp = desired_edge.get("trafficPolicy") or {}
        desired_rs = desired_tp.get("trafficRulesets") or {}
        if isinstance(desired_rs, dict) and desired_rs:
            return self._traffic_rulesets_need_update(desired_rs, device_info_dict)

        return False

    def _segment_attachments_need_update(self, desired_segments: Dict[str, Any], device_info_dict: Any) -> bool:
        d = self._device_dict(device_info_dict)

        for seg_name, seg_body in desired_segments.items():
            if not isinstance(seg_body, dict):
                return True
            tr = seg_body.get("trafficRuleset") or seg_body.get("traffic_ruleset")
            desired_ref: Any = None
            if isinstance(tr, dict):
                desired_ref = tr.get("ruleset")

            existing_seg = self._find_segment_object(d, str(seg_name))
            if existing_seg is None:
                LOG.info(
                    "[traffic-policy] LAN segment %s was not found in current device state; pushing desired update",
                    seg_name,
                )
                return True
            existing_ref = self._traffic_ruleset_ref_from_segment(existing_seg)

            if desired_ref is None:
                if existing_ref is not None:
                    LOG.info(
                        "[traffic-policy] LAN segment %s ruleset ref differs (desired cleared, existing=%r)",
                        seg_name,
                        existing_ref,
                    )
                    return True
                continue

            if not self._ruleset_refs_match(desired_ref, existing_ref):
                LOG.info(
                    "[traffic-policy] LAN segment %s ruleset ref differs (desired=%r, existing=%r, segment_keys=%s)",
                    seg_name,
                    desired_ref,
                    existing_ref,
                    list(existing_seg.keys()),
                )
                return True

        return False

    def _segment_payload_differs_with_retry(self, payload: Dict[str, Any], device_id: int) -> bool:
        for attempt in range(2):
            time.sleep(2)
            refreshed_info = self.gsdk.get_device_info(device_id)
            try:
                refreshed_dict = refreshed_info.to_dict()
            except Exception:
                refreshed_dict = refreshed_info
            if not self._payload_differs(payload, refreshed_dict):
                return False
            LOG.info(
                "[traffic-policy] Segment state still differs after refresh attempt %d for device_id=%s",
                attempt + 1,
                device_id,
            )
        return True

    @staticmethod
    def _existing_rule_from_entry(existing_entry: Any) -> Any:
        if not isinstance(existing_entry, dict):
            return None
        if "rule" in existing_entry:
            return existing_entry.get("rule")
        if any(k in existing_entry for k in ("seq", "match", "action")):
            return existing_entry
        return None

    def _desired_rules_need_update(self, desired_rules: Dict[str, Any], existing_rules: Any) -> bool:
        if not isinstance(desired_rules, dict):
            return True

        existing_map = existing_rules if isinstance(existing_rules, dict) else {}
        for rule_key, desired_entry in desired_rules.items():
            if not isinstance(desired_entry, dict):
                LOG.info("[traffic-policy] Desired rule entry %s is not a dict", rule_key)
                return True

            desired_rule = desired_entry.get("rule")
            existing_entry = existing_map.get(rule_key) if isinstance(existing_map, dict) else None
            existing_rule = self._existing_rule_from_entry(existing_entry)

            if desired_rule is None:
                if existing_rule is not None:
                    LOG.info("[traffic-policy] Rule %s exists and will be deleted", rule_key)
                    return True
                continue

            if not self._desired_matches_existing(desired_rule, existing_rule):
                mismatch = self._first_mismatch_path(desired_rule, existing_rule)
                LOG.info(
                    "[traffic-policy] Rule %s differs at %s (desired=%r existing=%r)",
                    rule_key,
                    mismatch,
                    self._value_at_path(desired_rule, mismatch),
                    self._value_at_path(existing_rule, mismatch),
                )
                return True

        return False

    def _traffic_rulesets_need_update(self, desired_rs: Dict[str, Any], device_info_dict: Any) -> bool:
        existing_rs = self._extract_rulesets_from_device(device_info_dict)
        LOG.info("[traffic-policy] existing trafficRulesets keys: %s", list(existing_rs.keys()))
        LOG.info("[traffic-policy] desired trafficRulesets keys: %s", list(desired_rs.keys()))

        for rs_id, desired_entry in desired_rs.items():
            if not isinstance(desired_entry, dict):
                LOG.info("[traffic-policy] Desired ruleset entry %s is not a dict", rs_id)
                return True
            desired_ruleset = desired_entry.get("ruleset")
            existing_entry = existing_rs.get(rs_id) if isinstance(existing_rs, dict) else None
            existing_ruleset = self._existing_ruleset_from_entry(existing_entry)
            existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, str(rs_id))

            if desired_ruleset is None:
                if existing_ruleset is not None:
                    LOG.info("[traffic-policy] Ruleset %s exists and will be deleted", rs_id)
                    return True
                continue

            desired_rules = desired_ruleset.get("rules") if isinstance(desired_ruleset, dict) else None
            if isinstance(desired_rules, dict) and desired_rules:
                existing_rules = (existing_ruleset or {}).get("rules") or {}
                if self._desired_rules_need_update(desired_rules, existing_rules):
                    return True
                desired_meta = {k: v for k, v in desired_ruleset.items() if k != "rules"}
                existing_meta = {k: v for k, v in (existing_ruleset or {}).items() if k != "rules"}
                if not self._desired_matches_existing(desired_meta, existing_meta):
                    mismatch = self._first_mismatch_path(desired_meta, existing_meta)
                    LOG.info("[traffic-policy] Ruleset %s metadata differs at %s", rs_id, mismatch)
                    return True
                continue

            if not self._desired_matches_existing(desired_ruleset, existing_ruleset):
                mismatch = self._first_mismatch_path(desired_ruleset, existing_ruleset)
                LOG.info(
                    "[traffic-policy] Ruleset %s differs at %s "
                    "(desired=%r existing=%r; desired_parent=%r existing_parent=%r)",
                    rs_id,
                    mismatch,
                    self._value_at_path(desired_ruleset, mismatch),
                    self._value_at_path(existing_ruleset, mismatch),
                    self._value_at_path(desired_ruleset, self._parent_path(mismatch)),
                    self._value_at_path(existing_ruleset, self._parent_path(mismatch)),
                )
                return True

        return False

    def _snapshot_rule_for_diff(self, rule: Any) -> Any:
        if rule is None:
            return None
        return self._normalize(rule)

    def _ruleset_rules_snapshot(self, ruleset: Any) -> Dict[str, Any]:
        if not isinstance(ruleset, dict):
            return {}
        rules = ruleset.get("rules") or {}
        if not isinstance(rules, dict):
            rules = self._coerce_existing_rules_map(rules)
        out_rules: Dict[str, Any] = {}
        for rule_key, entry in sorted(rules.items(), key=lambda kv: str(kv[0])):
            rule_body = self._existing_rule_from_entry(entry)
            out_rules[str(rule_key)] = self._snapshot_rule_for_diff(rule_body)
        snapshot: Dict[str, Any] = {"rules": out_rules}
        meta = {k: v for k, v in ruleset.items() if k != "rules"}
        if meta:
            snapshot["_meta"] = self._normalize(meta)
        return snapshot

    def _ruleset_diff_entry(
        self,
        desired_ruleset: Any,
        existing_ruleset: Any,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Build per-rule before/after for one ruleset (changed rules and metadata only)."""
        if desired_ruleset is None:
            if existing_ruleset is None:
                return None, None
            return self._ruleset_rules_snapshot(existing_ruleset), None

        if existing_ruleset is None:
            return None, self._ruleset_rules_snapshot(desired_ruleset)

        before: Dict[str, Any] = {}
        after: Dict[str, Any] = {}
        before_rules: Dict[str, Any] = {}
        after_rules: Dict[str, Any] = {}

        desired_rules = desired_ruleset.get("rules") if isinstance(desired_ruleset, dict) else None
        existing_rules = (existing_ruleset or {}).get("rules") or {}
        if not isinstance(existing_rules, dict):
            existing_rules = self._coerce_existing_rules_map(existing_rules)

        if isinstance(desired_rules, dict):
            for rule_key, desired_entry in sorted(desired_rules.items(), key=lambda kv: str(kv[0])):
                if not isinstance(desired_entry, dict):
                    continue
                desired_rule = desired_entry.get("rule")
                existing_entry = existing_rules.get(rule_key) if isinstance(existing_rules, dict) else None
                existing_rule = self._existing_rule_from_entry(existing_entry)

                if desired_rule is None:
                    if existing_rule is not None:
                        before_rules[str(rule_key)] = self._snapshot_rule_for_diff(existing_rule)
                        after_rules[str(rule_key)] = None
                elif existing_rule is None or not self._desired_matches_existing(desired_rule, existing_rule):
                    before_rules[str(rule_key)] = self._snapshot_rule_for_diff(existing_rule) if existing_rule else None
                    after_rules[str(rule_key)] = self._snapshot_rule_for_diff(desired_rule)

        if before_rules or after_rules:
            before["rules"] = before_rules
            after["rules"] = after_rules

        desired_meta = {k: v for k, v in desired_ruleset.items() if k != "rules"}
        existing_meta = {k: v for k, v in existing_ruleset.items() if k != "rules"}
        if not self._desired_matches_existing(desired_meta, existing_meta):
            before["_meta"] = self._normalize(existing_meta)
            after["_meta"] = self._normalize(desired_meta)

        if not before and not after:
            return None, None
        return before or None, after or None

    def _traffic_policy_diff(
        self, device_dict: Dict[str, Any], payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
        """Build before/after snapshots and branch label for ``diff_plan`` / ``--diff``."""
        desired_edge = as_dict(payload.get("edge"))
        before: Dict[str, Any] = {}
        after: Dict[str, Any] = {}

        desired_segments = desired_edge.get("segments")
        if isinstance(desired_segments, dict) and desired_segments:
            d = self._device_dict({"device": device_dict})
            before_segs: Dict[str, Any] = {}
            after_segs: Dict[str, Any] = {}
            for seg_name in sorted(desired_segments.keys()):
                existing_seg = self._find_segment_object(d, str(seg_name))
                before_segs[seg_name] = {"ruleset": self._traffic_ruleset_ref_from_segment(existing_seg)}
                seg_body = as_dict(desired_segments[seg_name])
                tr = as_dict(seg_body.get("trafficRuleset") or seg_body.get("traffic_ruleset"))
                after_segs[seg_name] = {"ruleset": tr.get("ruleset")}
            before["segments"] = before_segs
            after["segments"] = after_segs
            return before, after, "edge.segments"

        desired_tp = as_dict(desired_edge.get("trafficPolicy"))
        desired_rs = desired_tp.get("trafficRulesets")
        if isinstance(desired_rs, dict) and desired_rs:
            existing_rs = self._extract_rulesets_from_device({"device": device_dict})
            before_rs: Dict[str, Any] = {}
            after_rs: Dict[str, Any] = {}
            for key in sorted(desired_rs.keys()):
                existing_entry = existing_rs.get(key) if isinstance(existing_rs, dict) else None
                existing_ruleset = self._existing_ruleset_from_entry(existing_entry)
                existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, str(key))

                desired_entry = as_dict(desired_rs[key])
                desired_ruleset = desired_entry.get("ruleset")
                before_entry, after_entry = self._ruleset_diff_entry(desired_ruleset, existing_ruleset)
                if before_entry is not None or after_entry is not None:
                    before_rs[key] = before_entry
                    after_rs[key] = after_entry
            before["trafficRulesets"] = before_rs
            after["trafficRulesets"] = after_rs
            return before, after, "edge.trafficPolicy.trafficRulesets"

        return before, after, "edge"

    def _iter_device_payloads(
        self, config_yaml_file: str, operation: str
    ) -> Iterator[Tuple[int, str, Dict[str, Any], Dict[str, Any]]]:
        if operation not in (
            "configure",
            "deconfigure",
            "attach_to_lan_segments",
            "detach_from_lan_segments",
        ):
            raise ConfigurationError(f"Unsupported operation '{operation}'")

        enterprise = self.gsdk.enterprise_info["company_name"]
        by_name = self._load_devices(config_yaml_file)
        if not by_name:
            LOG.info("%s No '%s' entries to process in %s", _LOG_PREFIX, _YAML_KEY, config_yaml_file)
            return

        for device_name, device_cfg in by_name.items():
            device_id, device_dict = fetch_device_by_name(self.gsdk, device_name, enterprise)

            if operation in ("attach_to_lan_segments", "detach_from_lan_segments"):
                seg_cfg = device_cfg.get("segments")
                segments_map = self._segments_payload_from_yaml(seg_cfg, operation=operation)
                if not segments_map:
                    LOG.info("%s No 'segments' for %s, skipping", _LOG_PREFIX, device_name)
                    continue
                payload: Dict[str, Any] = {"edge": {"segments": segments_map}}
            else:
                tr_cfg = device_cfg.get("trafficRulesets")
                rulesets_map = self._rulesets_from_yaml(tr_cfg, operation=operation)
                if not rulesets_map:
                    LOG.info("%s No trafficRulesets for %s, skipping", _LOG_PREFIX, device_name)
                    continue
                payload = {"edge": {"trafficPolicy": {"trafficRulesets": rulesets_map}}}

            if "description" in device_cfg:
                payload["description"] = device_cfg.get("description", "")
            if "configurationMetadata" in device_cfg:
                meta = device_cfg.get("configurationMetadata")
                payload["configurationMetadata"] = meta if isinstance(meta, dict) else {"name": ""}

            yield device_id, device_name, payload, device_dict

    def apply_traffic_policy(self, config_yaml_file: str, operation: str) -> dict:
        result = new_apply_result()
        to_push: Dict[int, Dict[str, Any]] = {}
        configured_devices: List[str] = []
        diff_plan: List[Dict[str, Any]] = []
        for device_id, device_name, payload, device_dict in self._iter_device_payloads(
            config_yaml_file, operation=operation
        ):
            differs = self._payload_differs(payload, {"device": device_dict})
            if differs and (payload.get("edge") or {}).get("segments"):
                differs = self._segment_payload_differs_with_retry(payload, device_id)

            if not differs:
                LOG.info("%s ✓ No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            before, after, branch = self._traffic_policy_diff(device_dict, payload)
            to_push[device_id] = {"device_id": device_id, "payload": payload}
            configured_devices.append(device_name)
            diff_plan.append({"device": device_name, "branch": branch, "before": before, "after": after})

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

    def configure(self, config_yaml_file: str) -> dict:
        return self.apply_traffic_policy(config_yaml_file, operation="configure")

    def deconfigure(self, config_yaml_file: str) -> dict:
        return self.apply_traffic_policy(config_yaml_file, operation="deconfigure")

    def attach_to_lan_segments(self, config_yaml_file: str) -> dict:
        return self.apply_traffic_policy(config_yaml_file, operation="attach_to_lan_segments")

    def detach_from_lan_segments(self, config_yaml_file: str) -> dict:
        return self.apply_traffic_policy(config_yaml_file, operation="detach_from_lan_segments")
