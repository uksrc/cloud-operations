#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant device-level traffic policy objects under:
  edge.trafficPolicy.trafficRulesets
  edge.segments.<segment>.trafficRuleset (LAN segment association)
"""

DOCUMENTATION = r"""
---
module: graphiant_traffic_policy
short_description: Manage device traffic policy rulesets and LAN segment attachments
description:
  - Configure or delete device-level traffic policy rulesets under C(edge.trafficPolicy.trafficRulesets).
  - Attach or detach a named ruleset on LAN segments under C(edge.segments.<name>.trafficRuleset.ruleset).
  - Reads a structured YAML config file and builds the raw device-config payload in Python.
  - >-
    The configure workflow applies rulesets (C(operation=configure)) and attaches them to LAN segments
    (C(operation=attach_to_lan_segments)). The deconfigure workflow clears segment references
    (C(operation=detach_from_lan_segments)) and deletes listed rulesets (C(operation=deconfigure)).
  - "Configure is idempotent: compares intended rulesets to existing device state and skips push when already matched."
  - "Deconfigure deletes only the rulesets listed in the YAML by setting C(ruleset: null) per ruleset key."
  - >-
    Under C(configure), set C(state: absent) on a ruleset or individual rule in YAML to delete only
    that object (sends C(ruleset: null) or C(rule: null) in the payload). Omitted C(state) means
    C(present). This allows removing one rule without deconfiguring the whole ruleset.
  - "Attach/detach operations compare each listed segment's ruleset reference to the device and skip when unchanged."
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply would update
    at least one device. Use C(--diff) to preview C(details.diff_plan) and Ansible C(diff).
notes:
  - >-
    One YAML file may define both C(trafficRulesets) and C(segments). C(configure)/C(deconfigure) read
    C(trafficRulesets) only; C(attach_to_lan_segments)/C(detach_from_lan_segments) read C(segments) only.
    Run both steps for a full traffic policy lifecycle, or use the sample playbook tags C(configure) and
    C(deconfigure), which run attach/detach together with ruleset configure/deconfigure.
  - "This module manages traffic policies directly on devices (device config API), not portal-only objects."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - >-
    Deconfigure payload uses C(ruleset: null) per ruleset key; this module preserves nulls in the final
    payload pushed to the API.
  - >-
    Check mode (C(--check)) reads live device state, skips writes, sets C(changed) from whether an apply
    would update at least one device, and logs would-be payloads with a C([check_mode]) prefix when
    O(detailed_logs) is enabled.
  - >-
    Diff mode (C(--diff)) adds Ansible C(diff) (C(before) / C(after) strings) and C(details.diff_plan).
    Ruleset entries list only changed rules under C(rules) (plus C(_meta) when ruleset metadata changes).
    Segment attach/detach diffs show per-segment ruleset references under C(segments).
version_added: "26.5.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  traffic_policy_config_file:
    description:
      - Path to the traffic policy YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(trafficPolicyObject) (list of devices).
      - Each device may define C(trafficRulesets) and/or C(segments) in the same file.
      - C(configure)/C(deconfigure) use C(trafficRulesets); attach/detach operations use C(segments).
    type: str
    required: true
  operation:
    description:
      - Specific operation to perform.
      - >-
        C(configure) creates/updates rulesets listed under C(trafficRulesets). Pair with
        C(attach_to_lan_segments) (or the playbook C(configure) tag) to attach rulesets to LAN segments.
      - >-
        C(deconfigure) deletes listed rulesets by setting C(ruleset=null). Pair with
        C(detach_from_lan_segments) (or the playbook C(deconfigure) tag) to clear segment references first.
      - C(attach_to_lan_segments) sets C(edge.segments.<segment>.trafficRuleset.ruleset) from the YAML C(segments) map.
      - C(detach_from_lan_segments) clears the ruleset reference on each segment listed under C(segments).
    type: str
    required: false
    choices: [ configure, deconfigure, attach_to_lan_segments, detach_from_lan_segments ]
  state:
    description:
      - Desired state for traffic policy rulesets.
      - >-
        C(present) maps to C(configure) when C(operation) is omitted. For a full apply, also run
        C(attach_to_lan_segments) or use the sample playbook C(configure) tag.
      - >-
        C(absent) maps to C(deconfigure) when C(operation) is omitted. For a full teardown, also run
        C(detach_from_lan_segments) or use the sample playbook C(deconfigure) tag.
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
    description: Supports Ansible's C(--diff) for pending traffic policy updates.
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
# Configure workflow: rulesets, then attach to LAN segments (same YAML file).
- name: Configure device-level traffic policy rulesets
  graphiant.naas.graphiant_traffic_policy:
    operation: configure
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: traffic_policy_result
  no_log: true

- name: Attach traffic ruleset to LAN segments
  graphiant.naas.graphiant_traffic_policy:
    operation: attach_to_lan_segments
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# Deconfigure workflow: detach from LAN segments, then delete listed rulesets.
- name: Detach traffic ruleset from LAN segments
  graphiant.naas.graphiant_traffic_policy:
    operation: detach_from_lan_segments
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure device-level traffic policy rulesets
  graphiant.naas.graphiant_traffic_policy:
    operation: deconfigure
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# Preview pending changes without pushing (check mode)
- name: Preview traffic policy configure (dry run)
  graphiant.naas.graphiant_traffic_policy:
    operation: configure
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  check_mode: true
  register: traffic_policy_preview

# Preview per-rule diffs (run playbook with --diff or set diff: true on the task)
- name: Preview traffic policy rule changes
  graphiant.naas.graphiant_traffic_policy:
    operation: configure
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  diff: true
  register: traffic_policy_diff
  # details.diff_plan[].before/after.trafficRulesets.<name>.rules.<seq> — changed rules only

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
traffic_policy_config_file:
  description: The traffic policy config file used for the operation.
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
      C(edge.trafficPolicy.trafficRulesets) or C(edge.segments)), and normalized C(before) / C(after)
      snapshots. Ruleset branches list only changed rules under C(rules); ruleset metadata changes appear
      under C(_meta).
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
                f"graphiant_traffic_policy: manager {name!s} failed: {type(e).__name__}: {e!s}",
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
        traffic_policy_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=["configure", "deconfigure", "attach_to_lan_segments", "detach_from_lan_segments"],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["traffic_policy_config_file"]

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_traffic_policy: start operation={operation!r} "
                    f"traffic_policy_config_file={cfg_file!r} check_mode={module.check_mode!r}"
                ),
            )
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                "graphiant_traffic_policy: GraphiantConfig obtained; dispatching to traffic policy manager",
            )

        changed = False
        result_msg = ""

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.traffic_policy.configure,
                cfg_file,
                success_msg="Successfully configured device-level traffic policy rulesets",
                no_change_msg="Device-level traffic policy already matches desired state; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.traffic_policy.deconfigure,
                cfg_file,
                success_msg="Successfully deconfigured device-level traffic policy rulesets",
                no_change_msg="Device-level traffic policy rulesets already absent; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "attach_to_lan_segments":
            result = execute_with_logging(
                module,
                graphiant_config.traffic_policy.attach_to_lan_segments,
                cfg_file,
                success_msg="Successfully attached traffic ruleset(s) to LAN segment(s)",
                no_change_msg="LAN segment traffic ruleset references already match desired state",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "detach_from_lan_segments":
            result = execute_with_logging(
                module,
                graphiant_config.traffic_policy.detach_from_lan_segments,
                cfg_file,
                success_msg="Successfully detached traffic ruleset(s) from LAN segment(s)",
                no_change_msg="LAN segment traffic ruleset references already cleared",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        else:
            module.fail_json(
                msg=(
                    f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure, "
                    f"attach_to_lan_segments, detach_from_lan_segments."
                ),
                operation=operation,
            )
            return

        if params.get("detailed_logs"):
            preview = result_msg if len(result_msg) <= 200 else (result_msg[:200] + "…")
            ansible_module_log(
                module,
                f"graphiant_traffic_policy: success changed={changed!r} result_msg_preview={preview!r}",
            )
        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            traffic_policy_config_file=cfg_file,
            configured_devices=result.get("configured_devices", []),
            skipped_devices=result.get("skipped_devices", []),
            details=details,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        if module.params.get("detailed_logs"):
            import traceback

            ansible_module_log(
                module,
                f"graphiant_traffic_policy: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_traffic_policy: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
