"""
Security Policy Manager for Graphiant Playbooks.

Manages device-level security policy objects under:
  edge.trafficPolicy.securityRulesets
  edge.trafficPolicy.zones
- Build raw device-config payload in Python from a structured YAML file
- Idempotency: compare intended rulesets to current device state; skip push when already matched
- Check mode: read device state, skip writes, accurate ``changed``; ``diff_plan`` for ``--diff`` (per-rule)
- Deconfigure: delete only the rulesets listed in the YAML by setting ruleset=null per key
- Per-object state in YAML: ruleset or rule ``state: absent`` sends ``ruleset: null`` or ``rule: null``
  under ``configure``
- Rule match type (application vs network/L4) is mutually exclusive — one primary match per rule.
  Combining application and network/L4 keys in the same rule raises a validation error.
  Match type cannot be changed in place on the device API; delete the rule (``state: absent``)
  and add a new rule with the desired match criteria.

Zone association (directional zone pair ruleset reference):
  edge.trafficPolicy.zones.<fromZone>.zone.pairs.<toZone>.pair
- attach_to_zone_pairs / detach_from_zone_pairs read ``zones`` from YAML
- Configure workflow: ``configure`` (rulesets) then ``attach_to_zone_pairs`` (zones)
- Deconfigure workflow: ``detach_from_zone_pairs`` (zones) then ``deconfigure`` (rulesets)
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

SECURITY_POLICY_KEYS = ("trafficPolicy", "traffic_policy", "securityPolicy", "security_policy")
EDGE_POLICY_KEY = "trafficPolicy"
SECURITY_RULESETS_KEYS = ("securityRulesets", "security_rulesets")
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
# Fields sent on config PUT but omitted from device GET responses.
GET_COMPARE_SKIP_KEYS = frozenset(
    {
        "implicitRuleAction",
        "globalId",
        "isGlobalSync",
        "id",
        "index",
        "status",
        "errorMessage",
    }
)
METER_RATE_FIELDS = (
    "uplinkPolicerRate",
    "uplinkBurstRate",
    "downlinkPolicerRate",
    "downlinkBurstRate",
)
_METER_RATE_FIELDS_SET = frozenset(METER_RATE_FIELDS)
_APPLICATION_MATCH_INPUT_KEYS = frozenset(
    {
        "application",
        "applicationBuiltin",
        "application_builtin",
        "applicationCustom",
        "application_custom",
    }
)
_NETWORK_MATCH_INPUT_KEYS = frozenset(
    {
        "destinationNetwork",
        "destination_network",
        "sourceNetwork",
        "source_network",
        "sourcePort",
        "destinationPort",
        "ipProtocol",
        "ip_protocol",
        "protocol",
        "icmpType",
    }
)
_STATE_CHOICES = frozenset({"present", "absent"})
_LOG_PREFIX = "[security-policy]"
_YAML_KEY = "SecurityPolicyObject"


class SecurityPolicyManager(BaseManager):
    """
    Manage security policy rulesets and LAN-segment ruleset references via raw device-config payloads.
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
            missing_input_error="security_policy_config_file is required.",
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
            except Exception:
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
                    if cls._meter_rate_omitted_on_get(key):
                        continue
                    return False
                if cls._matches_omitted_default(key, desired_value, existing_value):
                    continue
                if key == "action" and cls._actions_equivalent_for_compare(desired_value, existing_value):
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
                    if cls._meter_rate_omitted_on_get(key):
                        continue
                    return child_path
                if cls._matches_omitted_default(key, desired_value, existing_value):
                    continue
                if key == "action" and cls._actions_equivalent_for_compare(desired_value, existing_value):
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

    def _traffic_policy_from_device(self, device_info_dict: Any) -> Dict[str, Any]:
        """Merge ``trafficPolicy`` from device GET (``device`` or ``device.edge``)."""
        d = self._device_dict(device_info_dict)
        edge = as_dict(d.get("edge"))
        merged: Dict[str, Any] = {}
        for container in (edge, d):
            tp = as_dict(self._first_present(container, SECURITY_POLICY_KEYS))
            if tp:
                merged.update(tp)
        return merged

    def _extract_rulesets_from_device(self, device_info_dict: Any) -> Dict[str, Any]:
        tp = self._traffic_policy_from_device(device_info_dict)
        rs = self._first_present(tp, SECURITY_RULESETS_KEYS)
        if rs is not None:
            return self._coerce_rulesets_map(rs)
        return {}

    @classmethod
    def _normalize_meter_rate_for_compare(cls, value: Any) -> Any:
        if isinstance(value, dict):
            rate = value.get("rate")
            if rate is not None and set(value.keys()) <= {"rate"}:
                return rate
        return value

    @classmethod
    def _normalize_action_for_compare(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            inner = value.get("action")
            if inner is not None:
                return str(inner).strip().lower()
            if len(value) == 1:
                only = next(iter(value.values()))
                if isinstance(only, str):
                    return only.strip().lower()
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized if normalized else None
        return value

    @classmethod
    def _actions_equivalent_for_compare(cls, desired: Any, existing: Any) -> bool:
        desired_action = cls._normalize_action_for_compare(desired)
        existing_action = cls._normalize_action_for_compare(existing)
        if desired_action == existing_action:
            return True
        # Device GET may return reject when YAML requests drop (silent deny).
        return desired_action == "drop" and existing_action == "reject"

    @classmethod
    def _meter_rate_omitted_on_get(cls, key: str) -> bool:
        """
        Meter policer/burst rates are sent on PUT but are often omitted from rule GET
        responses (including drop/reject rules and downlink rates that mirror uplink).
        """
        return key in _METER_RATE_FIELDS_SET

    @classmethod
    def _normalize_match_for_compare(cls, match: Any) -> Any:
        if not isinstance(match, dict):
            return match
        out = dict(match)
        ip_proto = out.get("ipProtocol")
        if ip_proto is None:
            ip_proto = out.get("ip_protocol")
        protocol = out.get("protocol")
        if ip_proto is None and isinstance(protocol, dict):
            nested = protocol.get("ipProtocol")
            if nested is None:
                nested = protocol.get("ip_protocol")
            if nested is not None:
                ip_proto = nested
        if ip_proto is not None:
            out["ipProtocol"] = str(ip_proto).strip().lower()
        out.pop("ip_protocol", None)
        # PUT normalization adds protocol.ipProtocol; GET often returns ipProtocol only.
        out.pop("protocol", None)
        return out

    @classmethod
    def _normalize_rule_for_compare(cls, rule: Any) -> Any:
        if not isinstance(rule, dict):
            return rule
        out = dict(rule)
        for field in METER_RATE_FIELDS:
            if field in out:
                out[field] = cls._normalize_meter_rate_for_compare(out[field])
        if "action" in out:
            normalized_action = cls._normalize_action_for_compare(out["action"])
            if normalized_action is not None:
                out["action"] = normalized_action
        if isinstance(out.get("match"), dict):
            out["match"] = cls._normalize_match_for_compare(out["match"])
        return out

    def _find_existing_ruleset_entry(self, existing_rs: Dict[str, Any], rs_id: str) -> Any:
        if not isinstance(existing_rs, dict):
            return None
        if rs_id in existing_rs:
            return existing_rs[rs_id]
        for key, entry in existing_rs.items():
            if str(key).endswith(f"-{rs_id}"):
                return entry
        for entry in existing_rs.values():
            body = self._existing_ruleset_from_entry(entry)
            name = (body or {}).get("name") if isinstance(body, dict) else None
            if name and self._ruleset_refs_match(rs_id, name):
                return entry
        return None

    def _ruleset_metadata_matches(self, desired_ruleset: Dict[str, Any], existing_ruleset: Any) -> bool:
        desired_meta = {k: v for k, v in desired_ruleset.items() if k != "rules" and k not in GET_COMPARE_SKIP_KEYS}
        existing_meta = {
            k: v for k, v in (existing_ruleset or {}).items() if k != "rules" and k not in GET_COMPARE_SKIP_KEYS
        }
        desired_name = desired_ruleset.get("name")
        if desired_name is not None:
            existing_name = (existing_ruleset or {}).get("name")
            if not self._ruleset_refs_match(desired_name, existing_name):
                return False
        desired_meta.pop("name", None)
        existing_meta.pop("name", None)
        return self._desired_matches_existing(desired_meta, existing_meta)

    @staticmethod
    def _ruleset_name_from_entry(entry: Any) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        ruleset_body = entry.get("ruleset")
        if isinstance(ruleset_body, dict):
            ruleset: Dict[str, Any] = ruleset_body
        else:
            ruleset = entry
        name = SecurityPolicyManager._first_present(ruleset, RULESET_REF_KEYS) or entry.get("name")
        return str(name).strip() if name else None

    @staticmethod
    def _coerce_rulesets_map(rulesets: Any) -> Dict[str, Any]:
        if not rulesets:
            return {}

        if isinstance(rulesets, dict):
            mapped: Dict[str, Any] = dict(rulesets)
            for key, entry in rulesets.items():
                name = SecurityPolicyManager._ruleset_name_from_entry(entry)
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
                name = SecurityPolicyManager._ruleset_name_from_entry(item)
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
    def _normalize_network_match_field(cls, field: str, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            if field in value or "match" in value:
                return value
        return {field: str(value).strip()}

    @classmethod
    def _normalize_content_filter(cls, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ConfigurationError("contentFilter must be a dict")
        if "match" in value:
            match_body = dict(value.get("match") or {})
            ids = match_body.get("domainCategoryIds")
            if ids is None:
                ids = match_body.get("domain_category_ids")
            if ids is not None:
                match_body["domainCategoryIds"] = list(ids)
                match_body.pop("domain_category_ids", None)
            return {"match": match_body}
        ids = value.get("domainCategoryIds")
        if ids is None:
            ids = value.get("domain_category_ids")
        if ids is not None:
            return {"match": {"domainCategoryIds": list(ids)}}
        return value

    @classmethod
    def _normalize_domain_list(cls, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ConfigurationError("domainList must be a dict")
        if "match" in value:
            match_body = dict(value.get("match") or {})
            wildcards = match_body.get("domainWildcards")
            if wildcards is None:
                wildcards = match_body.get("domain_wildcards")
            if wildcards is not None:
                match_body["domainWildcards"] = list(wildcards)
                match_body.pop("domain_wildcards", None)
            return {"match": match_body}
        wildcards = value.get("domainWildcards")
        if wildcards is None:
            wildcards = value.get("domain_wildcards")
        if wildcards is not None:
            return {"match": {"domainWildcards": list(wildcards)}}
        return value

    @classmethod
    def _normalize_application_match(cls, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ConfigurationError("application must be a dict")
        if "match" in value:
            match_body = dict(value.get("match") or {})
            builtin = match_body.get("builtin")
            if builtin is None:
                builtin = match_body.get("application_builtin") or match_body.get("applicationBuiltin")
            custom = match_body.get("custom")
            if custom is None:
                custom = match_body.get("application_custom") or match_body.get("applicationCustom")
        else:
            builtin = value.get("builtin")
            if builtin is None:
                builtin = value.get("application_builtin") or value.get("applicationBuiltin")
            custom = value.get("custom")
            if custom is None:
                custom = value.get("application_custom") or value.get("applicationCustom")
        if builtin is not None and custom is None:
            return {"match": {"builtin": str(builtin).strip()}}
        if custom is not None and builtin is None:
            return {"match": {"custom": str(custom).strip()}}
        normalized: Dict[str, Any] = {}
        if builtin is not None:
            normalized["builtin"] = str(builtin).strip()
        if custom is not None:
            normalized["custom"] = str(custom).strip()
        if normalized:
            return {"match": normalized}
        return value

    @classmethod
    def _prune_empty_match_fields(cls, out: Dict[str, Any]) -> Dict[str, Any]:
        for key in list(out.keys()):
            value = out[key]
            if value == {}:
                out.pop(key, None)
                continue
            if key == "application" and isinstance(value, dict):
                match_body = value.get("match")
                if not match_body:
                    out.pop(key, None)
        return out

    @classmethod
    def _raw_match_has_application(cls, match: Dict[str, Any]) -> bool:
        if not isinstance(match, dict):
            return False
        for key in _APPLICATION_MATCH_INPUT_KEYS:
            if key == "application":
                app = match.get("application")
                if isinstance(app, dict) and app:
                    return True
                continue
            if match.get(key) is not None:
                return True
        return False

    @classmethod
    def _raw_match_has_network(cls, match: Dict[str, Any]) -> bool:
        if not isinstance(match, dict):
            return False
        return any(match.get(key) is not None for key in _NETWORK_MATCH_INPUT_KEYS)

    @classmethod
    def _combined_raw_match_from_rule(cls, rule: Dict[str, Any]) -> Dict[str, Any]:
        combined = dict(rule.get("match") or {})
        for key in _APPLICATION_MATCH_INPUT_KEYS | _NETWORK_MATCH_INPUT_KEYS:
            if key in rule and key not in combined:
                combined[key] = rule[key]
        return combined

    @classmethod
    def _validate_exclusive_match_type(cls, match: Dict[str, Any], *, context: str) -> None:
        if cls._raw_match_has_application(match) and cls._raw_match_has_network(match):
            raise ConfigurationError(
                f"{context}: rule match cannot combine application and network/L4 criteria; "
                "use one match type per rule"
            )

    @classmethod
    def _normalize_match_body(cls, match: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize security rule match to the device-config API shape.

        Scalar networks become ``{sourceNetwork: "..."}`` / ``{destinationNetwork: "..."}``.
        Ports are string values. ``ipProtocol`` also sets ``protocol.ipProtocol``.
        Application uses ``application.match.builtin`` or ``application.match.custom``.
        """
        cls._validate_exclusive_match_type(match, context="rule match")
        out = dict(match)

        for field in ("sourceNetwork", "destinationNetwork"):
            if field in out and out[field] is not None:
                out[field] = cls._normalize_network_match_field(field, out[field])

        for port_field in ("sourcePort", "destinationPort"):
            if port_field in out and out[port_field] is not None:
                out[port_field] = str(out[port_field]).strip()

        ip_proto = out.get("ipProtocol")
        if ip_proto is None:
            ip_proto = out.get("ip_protocol")
        if ip_proto is not None:
            ip_proto = str(ip_proto).strip()
            out["ipProtocol"] = ip_proto
            out.pop("ip_protocol", None)
            protocol = out.get("protocol")
            if not isinstance(protocol, dict):
                out["protocol"] = {"ipProtocol": ip_proto}
            else:
                proto = dict(protocol)
                nested_proto = proto.get("ipProtocol")
                if nested_proto is None:
                    nested_proto = proto.get("ip_protocol")
                if nested_proto is None:
                    proto["ipProtocol"] = ip_proto
                else:
                    proto["ipProtocol"] = str(nested_proto).strip()
                    proto.pop("ip_protocol", None)
                out["protocol"] = proto

        if "icmpType" in out and out["icmpType"] is not None:
            out["icmpType"] = out["icmpType"]

        app_builtin = out.pop("applicationBuiltin", None)
        if app_builtin is None:
            app_builtin = out.pop("application_builtin", None)
        app_custom = out.pop("applicationCustom", None)
        if app_custom is None:
            app_custom = out.pop("application_custom", None)
        if app_builtin is not None or app_custom is not None:
            app_match: Dict[str, Any] = {}
            if app_builtin is not None:
                app_match["builtin"] = str(app_builtin).strip()
            if app_custom is not None:
                app_match["custom"] = str(app_custom).strip()
            out["application"] = {"match": app_match}

        if "application" in out:
            out["application"] = cls._normalize_application_match(out["application"])

        domain_category_ids = out.pop("domainCategoryIds", None)
        if domain_category_ids is None:
            domain_category_ids = out.pop("domain_category_ids", None)
        if domain_category_ids is not None and "contentFilter" not in out:
            out["contentFilter"] = {"match": {"domainCategoryIds": list(domain_category_ids)}}

        if "contentFilter" in out:
            out["contentFilter"] = cls._normalize_content_filter(out["contentFilter"])

        domain_wildcards = out.pop("domainWildcards", None)
        if domain_wildcards is None:
            domain_wildcards = out.pop("domain_wildcards", None)
        if domain_wildcards is not None and "domainList" not in out:
            out["domainList"] = {"match": {"domainWildcards": list(domain_wildcards)}}

        if "domainList" in out:
            out["domainList"] = cls._normalize_domain_list(out["domainList"])

        return cls._prune_empty_match_fields(out)

    @classmethod
    def _match_from_shorthand(cls, rule: Dict[str, Any]) -> Dict[str, Any]:
        match = dict(rule.get("match") or {})

        app_builtin = rule.pop("applicationBuiltin", None)
        if app_builtin is not None:
            cls._set_nested(match, ("application", "match", "builtin"), app_builtin)
            app_body = match.get("application")
            if isinstance(app_body, dict):
                app_match_body = app_body.get("match")
                if isinstance(app_match_body, dict):
                    app_match_body.pop("custom", None)

        app_custom = rule.pop("applicationCustom", None)
        if app_custom is not None:
            cls._set_nested(match, ("application", "match", "custom"), app_custom)
            app_body = match.get("application")
            if isinstance(app_body, dict):
                app_match_body = app_body.get("match")
                if isinstance(app_match_body, dict):
                    app_match_body.pop("builtin", None)

        for field_name in ("ipProtocol", "sourcePort", "destinationPort", "icmpType"):
            if field_name in rule:
                match[field_name] = rule.pop(field_name)

        for field_name in ("sourceNetwork", "destinationNetwork"):
            if field_name in rule:
                match[field_name] = rule.pop(field_name)

        dscp_code_point = rule.pop("dscpCodePoint", None)
        if dscp_code_point is not None:
            cls._set_nested(match, ("dscp", "match", "codePoint"), dscp_code_point)

        if not match:
            return {}
        return cls._normalize_match_body(match)

    @classmethod
    def _normalize_meter_rate(cls, value: Any) -> Any:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, (int, float, str)):
            rate = str(value).strip()
            if rate:
                return {"rate": int(rate)}
        return value

    @classmethod
    def _normalize_rule_body(cls, rule: Any) -> Any:
        if not isinstance(rule, dict):
            return rule

        out = dict(rule)
        cls._validate_exclusive_match_type(
            cls._combined_raw_match_from_rule(out),
            context=f"rule seq {out.get('seq', '?')}",
        )
        if isinstance(out.get("match"), dict):
            out["match"] = cls._normalize_match_body(dict(out["match"]))
        else:
            match = cls._match_from_shorthand(out)
            if match:
                out["match"] = match

        raw_action = out.pop("action", None)
        if isinstance(raw_action, str):
            action_val = raw_action.strip().lower()
            if action_val:
                out["action"] = action_val
        elif isinstance(raw_action, dict) and raw_action:
            out["action"] = raw_action

        for field in (
            "uplinkPolicerRate",
            "uplinkBurstRate",
            "downlinkPolicerRate",
            "downlinkBurstRate",
        ):
            if field in out:
                out[field] = cls._normalize_meter_rate(out[field])

        return out

    @classmethod
    def _normalize_implicit_rule_action(cls, value: Any) -> Any:
        if value is None:
            return None
        action = str(value).strip()
        if not action:
            return None
        return action.lower()

    def _normalize_ruleset_body(self, ruleset: Any) -> Any:
        if not isinstance(ruleset, dict):
            return ruleset
        out = dict(ruleset)
        ira = out.pop("implicitRuleAction", None)
        if ira is None:
            ira = out.pop("implicit_rule_action", None)
        normalized_ira = self._normalize_implicit_rule_action(ira)
        if normalized_ira is not None:
            out["implicitRuleAction"] = normalized_ira
        if "rules" in out:
            out["rules"] = self._rules_from_yaml(out.get("rules"))
        return out

    def _normalize_ruleset_entry(self, key: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(entry)
        ruleset = out.get("ruleset")
        if ruleset is not None:
            if not isinstance(ruleset, dict):
                raise ConfigurationError(f"securityRulesets['{key}'].ruleset must be a dict or null")
            normalized = self._normalize_ruleset_body(ruleset)
            if isinstance(normalized, dict) and not normalized.get("name"):
                normalized["name"] = key
            out["ruleset"] = normalized
        return out

    def _rulesets_from_yaml(self, tr_cfg: Any, operation: str) -> Dict[str, Any]:
        """
        Build the securityRulesets map for the device-config API.

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
                    raise ConfigurationError("securityRulesets dict keys must be non-empty strings")
                if operation == "deconfigure":
                    out[key] = {"ruleset": None}
                    continue
                if not isinstance(v, dict):
                    raise ConfigurationError(f"securityRulesets['{key}'] must be a dict")
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
                            raise ConfigurationError("securityRulesets list entry missing 'name' for deconfigure")
                        out[str(n).strip()] = {"ruleset": None}
                    else:
                        raise ConfigurationError("securityRulesets list entries must be str or dict for deconfigure")
                    continue
                if not isinstance(entry, dict):
                    raise ConfigurationError("securityRulesets list items must be dicts with a 'name' field")
                n = entry.get("name")
                if not n:
                    raise ConfigurationError("securityRulesets list entry missing 'name'")
                name = str(n).strip()
                rs_state = self._normalized_state(entry.get("state"), context=f"ruleset '{name}'")
                if rs_state == "absent":
                    out[name] = {"ruleset": None}
                    continue
                body = {k: val for k, val in entry.items() if k not in ("name", "state")}
                out[name] = {"ruleset": self._normalize_ruleset_body({"name": name, **body})}
            return out
        raise ConfigurationError("'securityRulesets' must be a dict or list")

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

    @staticmethod
    def _ruleset_refs_match(desired_ref: Any, existing_ref: Optional[str]) -> bool:
        desired = str(desired_ref).strip()
        existing = (existing_ref or "").strip()
        if desired == existing:
            return True
        # The API may return generated names like G-<device-id>-<ruleset-name>.
        return bool(desired and existing.endswith(f"-{desired}"))

    def _extract_zone_pairs_from_device(self, device_info_dict: Any) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """
        Normalize zone attachments from device GET or config shape.

        GET returns ``trafficPolicy.zonePairs`` as a flat list; config PUT uses
        ``trafficPolicy.zones`` nested maps.
        """
        tp = self._traffic_policy_from_device(device_info_dict)
        pairs: Dict[Tuple[str, str], Dict[str, Any]] = {}

        zone_pairs = tp.get("zonePairs") or tp.get("zone_pairs")
        if isinstance(zone_pairs, list):
            for item in zone_pairs:
                if not isinstance(item, dict):
                    continue
                inside = str(item.get("inside") or "").strip()
                outside = str(item.get("outside") or "").strip()
                if inside and outside:
                    pairs[(inside, outside)] = item

        zones = tp.get("zones")
        if isinstance(zones, dict):
            for inside, outside, ruleset, tcp_prot in self._iter_zone_pairs_from_zones_map(zones):
                pairs.setdefault(
                    (inside, outside),
                    {
                        "inside": inside,
                        "outside": outside,
                        "ruleset": ruleset,
                        "tcpProtection": tcp_prot,
                    },
                )
        return pairs

    def _extract_zones_from_device(self, device_info_dict: Any) -> Dict[str, Any]:
        zones = self._traffic_policy_from_device(device_info_dict).get("zones")
        return as_dict(zones) if isinstance(zones, dict) else {}

    @classmethod
    def _lookup_zone_pair(
        cls, pairs_map: Dict[Tuple[str, str], Dict[str, Any]], inside: str, outside: str
    ) -> Optional[Dict[str, Any]]:
        key = (inside, outside)
        if key in pairs_map:
            return pairs_map[key]
        inside_l = inside.lower()
        outside_l = outside.lower()
        for (zone_inside, zone_outside), pair in pairs_map.items():
            if zone_inside.lower() == inside_l and zone_outside.lower() == outside_l:
                return pair
        return None

    @classmethod
    def _pair_from_zones_map(cls, zones_map: Dict[str, Any], inside: str, outside: str) -> Optional[Dict[str, Any]]:
        zone_entry = zones_map.get(inside)
        if not isinstance(zone_entry, dict):
            return None
        zone = zone_entry.get("zone")
        if not isinstance(zone, dict):
            return None
        pairs = zone.get("pairs")
        if not isinstance(pairs, dict):
            return None
        pair_wrap = pairs.get(outside)
        if not isinstance(pair_wrap, dict):
            return None
        pair = pair_wrap.get("pair")
        return pair if isinstance(pair, dict) else None

    @classmethod
    def _set_zone_pair(
        cls,
        zones_out: Dict[str, Any],
        inside: str,
        outside: str,
        ruleset: Any,
        tcp_protection: bool,
    ) -> None:
        if inside not in zones_out:
            zones_out[inside] = {"zone": {"inside": inside, "pairs": {}}}
        zone_body = zones_out[inside]["zone"]
        if not isinstance(zone_body.get("pairs"), dict):
            zone_body["pairs"] = {}
        if ruleset is None:
            # Nullable wrapper delete/clear (same pattern as securityRulesets deconfigure).
            zone_body["pairs"][outside] = {}
            return
        zone_body["pairs"][outside] = {
            "pair": {
                "outside": outside,
                "ruleset": ruleset,
                "tcpProtection": tcp_protection,
            }
        }

    @classmethod
    def _zone_names_from_yaml_entry(cls, entry: Dict[str, Any]) -> Tuple[str, str]:
        from_zone = entry.get("fromZone") or entry.get("from_zone") or entry.get("inside")
        to_zone = entry.get("toZone") or entry.get("to_zone") or entry.get("outside")
        inside = str(from_zone or "").strip()
        outside = str(to_zone or "").strip()
        return inside, outside

    def _parse_zone_pair_list_entry(self, entry: Dict[str, Any], detach: bool) -> Tuple[str, str, Any, bool]:
        inside, outside = self._zone_names_from_yaml_entry(entry)
        if not inside or not outside:
            raise ConfigurationError("zones list entry requires non-empty 'fromZone' and 'toZone'")

        state = entry.get("state")
        if detach or state == "absent":
            ruleset: Any = None
        else:
            raw_ruleset = entry.get("ruleset")
            if raw_ruleset is None:
                raise ConfigurationError(f"zones pair {inside}->{outside} requires 'ruleset' when attaching")
            ruleset = str(raw_ruleset).strip()
            if not ruleset:
                raise ConfigurationError(f"zones pair {inside}->{outside}: ruleset name must be non-empty")

        tcp = entry.get("tcpProtection")
        if tcp is None:
            tcp = entry.get("tcp_protection", False)
        return inside, outside, ruleset, bool(tcp)

    @classmethod
    def _is_api_zones_dict(cls, zones_cfg: Dict[str, Any]) -> bool:
        for value in zones_cfg.values():
            if isinstance(value, dict) and "zone" in value:
                return True
        return False

    def _zones_payload_from_yaml(self, zones_cfg: Any, operation: str) -> Dict[str, Any]:
        """
        Build edge.trafficPolicy.zones map with directional zone pairs (fromZone -> toZone only).

        YAML list shape (recommended):
          - fromZone: zone-DIA
            toZone: zone-lan-segment-3
            ruleset: new-ruleset-0
            tcpProtection: false

        Or pass the API zones dict directly (keys are inside zone names).
        """
        if zones_cfg is None:
            return {}
        detach = operation == "detach_from_zone_pairs"

        if isinstance(zones_cfg, dict):
            if self._is_api_zones_dict(zones_cfg):
                if detach:
                    out: Dict[str, Any] = {}
                    for inside_key, zone_entry in zones_cfg.items():
                        if not isinstance(zone_entry, dict):
                            continue
                        zone = zone_entry.get("zone")
                        if not isinstance(zone, dict):
                            continue
                        inside = str(zone.get("inside") or inside_key).strip()
                        pairs = zone.get("pairs")
                        if not isinstance(pairs, dict):
                            continue
                        for outside_key, pair_wrap in pairs.items():
                            pair = (pair_wrap or {}).get("pair") if isinstance(pair_wrap, dict) else {}
                            outside = str((pair or {}).get("outside") or outside_key).strip()
                            tcp = bool((pair or {}).get("tcpProtection", False))
                            if inside and outside:
                                self._set_zone_pair(out, inside, outside, None, tcp)
                    return out
                return dict(zones_cfg)
            raise ConfigurationError("'zones' dict must use API shape with 'zone' entries")

        if isinstance(zones_cfg, list):
            zones_out: Dict[str, Any] = {}
            for raw_entry in zones_cfg:
                if not isinstance(raw_entry, dict):
                    raise ConfigurationError("zones list entries must be dicts")
                inside, outside, ruleset, tcp_prot = self._parse_zone_pair_list_entry(raw_entry, detach)
                self._set_zone_pair(zones_out, inside, outside, ruleset, tcp_prot)
            return zones_out

        raise ConfigurationError("'zones' must be a list of zone pairs or an API zones dict")

    @classmethod
    def _iter_zone_pairs_from_zones_map(cls, zones_map: Dict[str, Any]) -> Iterator[Tuple[str, str, Any, bool]]:
        for inside_key, zone_entry in zones_map.items():
            if not isinstance(zone_entry, dict):
                continue
            zone = zone_entry.get("zone")
            if not isinstance(zone, dict):
                continue
            inside = str(zone.get("inside") or inside_key).strip()
            pairs = zone.get("pairs")
            if not isinstance(pairs, dict):
                continue
            for outside_key, pair_wrap in pairs.items():
                if not isinstance(pair_wrap, dict):
                    continue
                pair = pair_wrap.get("pair")
                if pair is None:
                    if pair_wrap:
                        continue
                    outside = str(outside_key).strip()
                    if inside and outside:
                        yield inside, outside, None, False
                    continue
                if not isinstance(pair, dict):
                    continue
                outside = str(pair.get("outside") or outside_key).strip()
                if not inside or not outside:
                    continue
                yield inside, outside, pair.get("ruleset"), bool(pair.get("tcpProtection", False))

    def _pair_ruleset_cleared(self, pair: Optional[Dict[str, Any]]) -> bool:
        if pair is None:
            return True
        return self._coerce_ruleset_ref(pair.get("ruleset")) is None

    def _zone_pair_matches(
        self,
        pairs_map: Dict[Tuple[str, str], Dict[str, Any]],
        inside: str,
        outside: str,
        desired_ruleset: Any,
        desired_tcp: bool,
    ) -> bool:
        if desired_ruleset is None:
            pair = self._lookup_zone_pair(pairs_map, inside, outside)
            return self._pair_ruleset_cleared(pair)

        pair = self._lookup_zone_pair(pairs_map, inside, outside)
        if pair is None:
            return False

        ref = self._coerce_ruleset_ref(pair.get("ruleset"))
        if not self._ruleset_refs_match(desired_ruleset, ref):
            return False
        if bool(pair.get("tcpProtection")) != desired_tcp:
            return False
        return True

    def _zone_attachments_need_update(self, desired_zones: Dict[str, Any], device_info_dict: Any) -> bool:
        existing_pairs = self._extract_zone_pairs_from_device(device_info_dict)
        for inside, outside, ruleset, tcp_prot in self._iter_zone_pairs_from_zones_map(desired_zones):
            if not self._zone_pair_matches(existing_pairs, inside, outside, ruleset, tcp_prot):
                LOG.info(
                    "[security-policy] Zone pair %s->%s differs (desired ruleset=%r tcpProtection=%r)",
                    inside,
                    outside,
                    ruleset,
                    tcp_prot,
                )
                return True
        return False

    def _payload_differs(self, desired_payload: Dict[str, Any], device_info_dict: Any) -> bool:
        desired_edge = (desired_payload or {}).get("edge") or {}
        desired_tp = desired_edge.get(EDGE_POLICY_KEY) or {}
        desired_zones = desired_tp.get("zones") or {}
        if isinstance(desired_zones, dict) and desired_zones:
            return self._zone_attachments_need_update(desired_zones, device_info_dict)

        desired_rs = desired_tp.get("securityRulesets") or {}
        if isinstance(desired_rs, dict) and desired_rs:
            return self._security_rulesets_need_update(desired_rs, device_info_dict)

        return False

    def _zone_payload_differs_with_retry(self, payload: Dict[str, Any], device_id: int) -> bool:
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
                "[security-policy] Zone state still differs after refresh attempt %d for device_id=%s",
                attempt + 1,
                device_id,
            )
        return True

    def _ruleset_payload_differs_with_retry(self, payload: Dict[str, Any], device_id: int) -> bool:
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
                "[security-policy] Ruleset state still differs after refresh attempt %d for device_id=%s",
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
                LOG.info("[security-policy] Desired rule entry %s is not a dict", rule_key)
                return True

            desired_rule = desired_entry.get("rule")
            existing_entry = existing_map.get(rule_key) if isinstance(existing_map, dict) else None
            existing_rule = self._existing_rule_from_entry(existing_entry)

            if desired_rule is None:
                if existing_rule is not None:
                    LOG.info("[security-policy] Rule %s exists and will be deleted", rule_key)
                    return True
                continue

            if not self._desired_matches_existing(
                self._normalize_rule_for_compare(desired_rule),
                self._normalize_rule_for_compare(existing_rule),
            ):
                mismatch = self._first_mismatch_path(desired_rule, existing_rule)
                LOG.info(
                    "[security-policy] Rule %s differs at %s (desired=%r existing=%r)",
                    rule_key,
                    mismatch,
                    self._value_at_path(desired_rule, mismatch),
                    self._value_at_path(existing_rule, mismatch),
                )
                return True

        return False

    def _security_rulesets_need_update(self, desired_rs: Dict[str, Any], device_info_dict: Any) -> bool:
        existing_rs = self._extract_rulesets_from_device(device_info_dict)
        LOG.info("[security-policy] existing securityRulesets keys: %s", list(existing_rs.keys()))
        LOG.info("[security-policy] desired securityRulesets keys: %s", list(desired_rs.keys()))

        for rs_id, desired_entry in desired_rs.items():
            if not isinstance(desired_entry, dict):
                LOG.info("[security-policy] Desired ruleset entry %s is not a dict", rs_id)
                return True
            desired_ruleset = desired_entry.get("ruleset")
            existing_entry = self._find_existing_ruleset_entry(existing_rs, str(rs_id))
            existing_ruleset = self._existing_ruleset_from_entry(existing_entry)
            existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, str(rs_id))

            if desired_ruleset is None:
                if existing_ruleset is not None:
                    LOG.info("[security-policy] Ruleset %s exists and will be deleted", rs_id)
                    return True
                continue

            desired_rules = desired_ruleset.get("rules") if isinstance(desired_ruleset, dict) else None
            if isinstance(desired_rules, dict) and desired_rules:
                existing_rules = (existing_ruleset or {}).get("rules") or {}
                if self._desired_rules_need_update(desired_rules, existing_rules):
                    return True
                if not self._ruleset_metadata_matches(desired_ruleset, existing_ruleset):
                    mismatch = self._first_mismatch_path(
                        {k: v for k, v in desired_ruleset.items() if k != "rules" and k not in GET_COMPARE_SKIP_KEYS},
                        {
                            k: v
                            for k, v in (existing_ruleset or {}).items()
                            if k != "rules" and k not in GET_COMPARE_SKIP_KEYS
                        },
                    )
                    LOG.info("[security-policy] Ruleset %s metadata differs at %s", rs_id, mismatch)
                    return True
                continue

            if not self._ruleset_metadata_matches(
                desired_ruleset if isinstance(desired_ruleset, dict) else {},
                existing_ruleset,
            ):
                mismatch = self._first_mismatch_path(desired_ruleset, existing_ruleset)
                LOG.info(
                    "[security-policy] Ruleset %s differs at %s "
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
        return self._normalize_rule_for_compare(rule)

    def _ruleset_meta_for_diff(self, ruleset: Any) -> Dict[str, Any]:
        if not isinstance(ruleset, dict):
            return {}
        meta = {k: v for k, v in ruleset.items() if k != "rules" and k not in GET_COMPARE_SKIP_KEYS}
        return self._normalize(meta)

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
        meta = self._ruleset_meta_for_diff(ruleset)
        if meta:
            snapshot["_meta"] = meta
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
                elif existing_rule is None or not self._desired_matches_existing(
                    self._normalize_rule_for_compare(desired_rule),
                    self._normalize_rule_for_compare(existing_rule),
                ):
                    before_rules[str(rule_key)] = self._snapshot_rule_for_diff(existing_rule) if existing_rule else None
                    after_rules[str(rule_key)] = self._snapshot_rule_for_diff(desired_rule)

        if before_rules or after_rules:
            before["rules"] = before_rules
            after["rules"] = after_rules

        if not self._ruleset_metadata_matches(desired_ruleset, existing_ruleset):
            before["_meta"] = self._ruleset_meta_for_diff(existing_ruleset)
            after["_meta"] = self._ruleset_meta_for_diff(desired_ruleset)

        if not before and not after:
            return None, None
        return before or None, after or None

    def _security_policy_diff(
        self, device_dict: Dict[str, Any], payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
        """Build before/after snapshots and branch label for ``diff_plan`` / ``--diff``."""
        desired_edge = as_dict(payload.get("edge"))
        desired_tp = as_dict(desired_edge.get(EDGE_POLICY_KEY))
        before: Dict[str, Any] = {}
        after: Dict[str, Any] = {}

        desired_zones = desired_tp.get("zones")
        if isinstance(desired_zones, dict) and desired_zones:
            existing_pairs = self._extract_zone_pairs_from_device({"device": device_dict})
            before_pairs: Dict[str, Any] = {}
            after_pairs: Dict[str, Any] = {}
            for inside, outside, ruleset, tcp_prot in self._iter_zone_pairs_from_zones_map(desired_zones):
                pair_key = f"{inside}->{outside}"
                existing = self._lookup_zone_pair(existing_pairs, inside, outside)
                before_pairs[pair_key] = {
                    "ruleset": self._coerce_ruleset_ref((existing or {}).get("ruleset")),
                    "tcpProtection": bool((existing or {}).get("tcpProtection", False)),
                }
                after_pairs[pair_key] = {
                    "ruleset": self._coerce_ruleset_ref(ruleset),
                    "tcpProtection": tcp_prot,
                }
            before["zones"] = before_pairs
            after["zones"] = after_pairs
            return before, after, "edge.trafficPolicy.zones"

        desired_rs = desired_tp.get("securityRulesets")
        if isinstance(desired_rs, dict) and desired_rs:
            existing_rs = self._extract_rulesets_from_device({"device": device_dict})
            before_rs: Dict[str, Any] = {}
            after_rs: Dict[str, Any] = {}
            for key in sorted(desired_rs.keys()):
                existing_entry = self._find_existing_ruleset_entry(existing_rs, str(key))
                existing_ruleset = self._existing_ruleset_from_entry(existing_entry)
                existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, str(key))

                desired_entry = as_dict(desired_rs[key])
                desired_ruleset = desired_entry.get("ruleset")
                before_entry, after_entry = self._ruleset_diff_entry(desired_ruleset, existing_ruleset)
                if before_entry is not None or after_entry is not None:
                    before_rs[key] = before_entry
                    after_rs[key] = after_entry
            before["securityRulesets"] = before_rs
            after["securityRulesets"] = after_rs
            return before, after, "edge.trafficPolicy.securityRulesets"

        return before, after, "edge"

    def _iter_device_payloads(
        self, config_yaml_file: str, operation: str
    ) -> Iterator[Tuple[int, str, Dict[str, Any], Dict[str, Any]]]:
        if operation not in (
            "configure",
            "deconfigure",
            "attach_to_zone_pairs",
            "detach_from_zone_pairs",
        ):
            raise ConfigurationError(f"Unsupported operation '{operation}'")

        enterprise = self.gsdk.enterprise_info["company_name"]
        by_name = self._load_devices(config_yaml_file)
        if not by_name:
            LOG.info("%s No '%s' entries to process in %s", _LOG_PREFIX, _YAML_KEY, config_yaml_file)
            return

        for device_name, device_cfg in by_name.items():
            device_id, device_dict = fetch_device_by_name(self.gsdk, device_name, enterprise)

            payload: Dict[str, Any]
            if operation in ("attach_to_zone_pairs", "detach_from_zone_pairs"):
                zones_cfg = device_cfg.get("zones")
                zones_map = self._zones_payload_from_yaml(zones_cfg, operation=operation)
                if not zones_map:
                    LOG.info("%s No 'zones' for %s, skipping", _LOG_PREFIX, device_name)
                    continue
                payload = {"edge": {EDGE_POLICY_KEY: {"zones": zones_map}}}
            else:
                tr_cfg = device_cfg.get("securityRulesets")
                rulesets_map = self._rulesets_from_yaml(tr_cfg, operation=operation)
                if not rulesets_map:
                    LOG.info("%s No securityRulesets for %s, skipping", _LOG_PREFIX, device_name)
                    continue
                payload = {"edge": {EDGE_POLICY_KEY: {"securityRulesets": rulesets_map}}}

            if "description" in device_cfg:
                payload["description"] = device_cfg.get("description", "")
            if "configurationMetadata" in device_cfg:
                meta = device_cfg.get("configurationMetadata")
                payload["configurationMetadata"] = meta if isinstance(meta, dict) else {"name": ""}

            yield device_id, device_name, payload, device_dict

    def apply_security_policy(self, config_yaml_file: str, operation: str) -> dict:
        result = new_apply_result()
        to_push: Dict[int, Dict[str, Any]] = {}
        configured_devices: List[str] = []
        diff_plan: List[Dict[str, Any]] = []
        for device_id, device_name, payload, device_dict in self._iter_device_payloads(
            config_yaml_file, operation=operation
        ):
            differs = self._payload_differs(payload, {"device": device_dict})
            desired_tp = (payload.get("edge") or {}).get(EDGE_POLICY_KEY) or {}
            desired_zones = desired_tp.get("zones")
            desired_rs = desired_tp.get("securityRulesets")
            if differs and isinstance(desired_zones, dict) and desired_zones:
                differs = self._zone_payload_differs_with_retry(payload, device_id)
            elif differs and isinstance(desired_rs, dict) and desired_rs:
                differs = self._ruleset_payload_differs_with_retry(payload, device_id)

            if not differs:
                LOG.info("%s ✓ No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            before, after, branch = self._security_policy_diff(device_dict, payload)
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
        return self.apply_security_policy(config_yaml_file, operation="configure")

    def deconfigure(self, config_yaml_file: str) -> dict:
        return self.apply_security_policy(config_yaml_file, operation="deconfigure")

    def attach_to_zone_pairs(self, config_yaml_file: str) -> dict:
        return self.apply_security_policy(config_yaml_file, operation="attach_to_zone_pairs")

    def detach_from_zone_pairs(self, config_yaml_file: str) -> dict:
        return self.apply_security_policy(config_yaml_file, operation="detach_from_zone_pairs")
