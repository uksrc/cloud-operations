#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant device-level security policy objects under:
  edge.trafficPolicy.securityRulesets
  edge.trafficPolicy.zones (zone pair association)
"""

DOCUMENTATION = r"""
---
module: graphiant_security_policy
short_description: Manage device security policy rulesets and zone pair attachments
description:
  - Configure or delete device-level security policy rulesets under C(edge.trafficPolicy.securityRulesets).
  - Attach or detach a named ruleset on zone pairs under C(edge.trafficPolicy.zones).
  - Reads a structured YAML config file and builds the raw device-config payload in Python.
  - >-
    The configure workflow applies rulesets (C(operation=configure)) and attaches them to zone pairs
    (C(operation=attach_to_zone_pairs)). The deconfigure workflow clears zone pair references
    (C(operation=detach_from_zone_pairs)) and deletes listed rulesets (C(operation=deconfigure)).
  - "Configure is idempotent: compares intended rulesets to existing device state and skips push when already matched."
  - "Deconfigure deletes only the rulesets listed in the YAML by setting C(ruleset: null) per ruleset key."
  - >-
    Under C(configure), set C(state: absent) on a ruleset or individual rule in YAML to delete only
    that object (sends C(ruleset: null) or C(rule: null) in the payload). Omitted C(state) means
    C(present).
  - >-
    Rule C(action) (per rule): C(accept), C(reject), C(inspect), or C(drop). Ruleset
    C(implicitRuleAction) (catch-all for unmatched traffic): C(accept) or C(reject) only.
    Values are normalized to lowercase strings in the device-config payload.
  - >-
    Each rule supports one primary match type: application (C(applicationBuiltin) /
    C(applicationCustom)) or network/L4 (C(ipProtocol), C(sourceNetwork),
    C(destinationNetwork), ports). Combining both in the same rule is rejected.
  - >-
    You cannot change a rule's primary match type in place (for example, from C(applicationBuiltin)
    to C(ipProtocol) / C(destinationNetwork), or the reverse). The device API merges rule updates
    and leaves stale match criteria. Delete the rule (C(state: absent)) and add a new rule with
    the desired match instead.
  - "Attach/detach operations compare each listed zone pair's ruleset reference to the device and skip when unchanged."
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply would update
    at least one device. Use C(--diff) to preview C(details.diff_plan) and Ansible C(diff).
notes:
  - >-
    One YAML file may define both C(securityRulesets) and C(zones). C(configure)/C(deconfigure) read
    C(securityRulesets) only; C(attach_to_zone_pairs)/C(detach_from_zone_pairs) read C(zones) only.
    Run both steps for a full security policy lifecycle, or use the sample playbook tags C(configure) and
    C(deconfigure).
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - >-
    Check mode (C(--check)) reads live device state, skips writes, sets C(changed) from whether an apply
    would update at least one device, and logs would-be payloads with a C([check_mode]) prefix when
    O(detailed_logs) is enabled.
  - >-
    Diff mode (C(--diff)) adds Ansible C(diff) (C(before) / C(after) strings) and C(details.diff_plan).
    Ruleset entries list only changed rules under C(rules) (plus C(_meta) when ruleset metadata changes).
    Zone pair attach/detach diffs show per-pair ruleset references under C(zones).
version_added: "26.6.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  security_policy_config_file:
    description:
      - Path to the security policy YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(SecurityPolicyObject) (list of devices).
      - Each device may define C(securityRulesets) and/or C(zones) in the same file.
    type: str
    required: true
  operation:
    description:
      - Specific operation to perform.
      - C(configure) creates/updates rulesets listed under C(securityRulesets).
      - C(deconfigure) deletes listed rulesets by setting C(ruleset=null).
      - >-
        C(attach_to_zone_pairs) sets C(edge.trafficPolicy.zones) from the YAML C(zones) list
        (each entry uses C(fromZone), C(toZone), and C(ruleset)).
      - C(detach_from_zone_pairs) clears ruleset references on each zone pair listed under C(zones).
    type: str
    required: false
    choices: [ configure, deconfigure, attach_to_zone_pairs, detach_from_zone_pairs ]
  state:
    description:
      - Desired state for security policy rulesets.
      - C(present) maps to C(configure) when C(operation) is omitted.
      - C(absent) maps to C(deconfigure) when C(operation) is omitted.
    type: str
    required: false
    default: present
    choices: [ present, absent ]
  detailed_logs:
    description:
      - Enable detailed logging.
    type: bool
    default: false
attributes:
  check_mode:
    description: Supports check mode.
    support: full
    details: >
      In check mode, no configuration is pushed to devices, but the module still reads current
      device state to determine whether changes would be made. Payloads that would be pushed are
      logged with a C([check_mode]) prefix.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending security policy updates.
    support: full
    details: >
      When the playbook runs with C(--diff) and a device would change, the module returns a C(diff)
      dictionary (C(before) / C(after) strings). Structured entries are also in C(details.diff_plan).
      Ruleset diffs list only changed rules under C(rules) (plus C(_meta) when ruleset metadata changes).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 25.12.1
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure device-level security policy rulesets
  graphiant.naas.graphiant_security_policy:
    operation: configure
    security_policy_config_file: "sample_device_security_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Attach security ruleset to zone pairs
  graphiant.naas.graphiant_security_policy:
    operation: attach_to_zone_pairs
    security_policy_config_file: "sample_device_security_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# Preview pending changes without pushing (check mode)
- name: Preview security policy configure (dry run)
  graphiant.naas.graphiant_security_policy:
    operation: configure
    security_policy_config_file: "sample_device_security_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  check_mode: true
  register: security_policy_preview

# Preview per-rule diffs (run playbook with --diff or set diff: true on the task)
- name: Preview security policy rule changes
  graphiant.naas.graphiant_security_policy:
    operation: configure
    security_policy_config_file: "sample_device_security_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  diff: true
  register: security_policy_diff
  # details.diff_plan[].before/after.securityRulesets.<name>.rules.<seq> — changed rules only
"""

RETURN = r"""
msg:
  description: Result message (includes detailed logs when enabled).
  type: str
  returned: always
changed:
  description:
    - Whether the operation would push config to at least one device.
    - In check mode (C(--check)), no configuration is pushed, but V(changed) reflects whether changes would be made.
  type: bool
  returned: always
operation:
  description: The operation performed.
  type: str
  returned: always
security_policy_config_file:
  description: The security policy config file used for the operation.
  type: str
  returned: always
configured_devices:
  description: Device names where configuration was pushed (when changed=true).
  type: list
  elements: str
  returned: when supported
skipped_devices:
  description: Device names that were skipped because desired state already matched.
  type: list
  elements: str
  returned: when supported
details:
  description:
    - Raw manager result details (includes C(diff_plan), configured/skipped device lists).
    - >-
      Each C(diff_plan) entry has C(device), C(branch) (for example
      C(edge.trafficPolicy.securityRulesets) or C(edge.trafficPolicy.zones)), and normalized C(before) /
      C(after) snapshots. Ruleset branches list only changed rules under C(rules); ruleset metadata
      changes appear under C(_meta). Zone pair branches list C(ruleset) and C(tcpProtection) per pair.
  type: dict
  returned: when supported
diff:
  description:
    - Ansible diff output when the playbook runs with C(--diff) and at least one device would change.
    - Built from C(details.diff_plan) as JSON C(before) / C(after) strings per device and branch.
  type: dict
  returned: when diff mode is enabled and C(details.diff_plan) is non-empty
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    ansible_module_log,
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    no_change_msg = kwargs.pop("no_change_msg", "No changes needed")
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        if module.params.get("detailed_logs"):
            name = getattr(func, "__name__", str(func))
            ansible_module_log(
                module,
                f"graphiant_security_policy: manager {name!s} failed: {type(e).__name__}: {e!s}",
            )
        raise
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []
        msg = success_msg if changed else no_change_msg
        if not changed and skipped:
            msg += f" (skipped {len(skipped)} device(s))"
        return {
            "changed": changed,
            "result_msg": msg,
            "details": result,
            "configured_devices": configured,
            "skipped_devices": skipped,
        }
    return {"changed": True, "result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        security_policy_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=["configure", "deconfigure", "attach_to_zone_pairs", "detach_from_zone_pairs"],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["security_policy_config_file"]

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_security_policy: start operation={operation!r} "
                    f"security_policy_config_file={cfg_file!r} check_mode={module.check_mode!r}"
                ),
            )
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        manager = graphiant_config.security_policy

        if operation == "configure":
            result = execute_with_logging(
                module,
                manager.configure,
                cfg_file,
                success_msg="Successfully configured device-level security policy rulesets",
                no_change_msg="Device-level security policy already matches desired state; no changes needed",
            )
        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                manager.deconfigure,
                cfg_file,
                success_msg="Successfully deconfigured device-level security policy rulesets",
                no_change_msg="Device-level security policy rulesets already absent; no changes needed",
            )
        elif operation == "attach_to_zone_pairs":
            result = execute_with_logging(
                module,
                manager.attach_to_zone_pairs,
                cfg_file,
                success_msg="Successfully attached security ruleset(s) to zone pair(s)",
                no_change_msg="Zone pair security ruleset references already match desired state",
            )
        elif operation == "detach_from_zone_pairs":
            result = execute_with_logging(
                module,
                manager.detach_from_zone_pairs,
                cfg_file,
                success_msg="Successfully detached security ruleset(s) from zone pair(s)",
                no_change_msg="Zone pair security ruleset references already cleared",
            )
        else:
            module.fail_json(
                msg=(
                    f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure, "
                    f"attach_to_zone_pairs, detach_from_zone_pairs."
                ),
                operation=operation,
            )
            return

        details = result.get("details") or {}
        exit_payload = dict(
            changed=result["changed"],
            msg=result["result_msg"],
            operation=operation,
            security_policy_config_file=cfg_file,
            configured_devices=result.get("configured_devices", []),
            skipped_devices=result.get("skipped_devices", []),
            details=details,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        ansible_module_log(
            module,
            f"graphiant_security_policy: failed {type(e).__name__}: {e!s}",
        )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
