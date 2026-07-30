#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant prefix and port lists under:
  edge.trafficPolicy.networkLists
  edge.trafficPolicy.portLists
"""

DOCUMENTATION = r"""
---
module: graphiant_prefix_port_list
short_description: >-
  Manage Graphiant prefix and port lists (edge.trafficPolicy.networkLists,
  edge.trafficPolicy.portLists)
description:
  - >-
    Create or delete prefix and port lists under edge traffic policy
    (edge.trafficPolicy.networkLists, edge.trafficPolicy.portLists).
  - Reads a structured YAML config file and builds the raw device-config payload in Python.
  - All operations are idempotent and safe to run multiple times.
notes:
  - "Prefix and Port List Operations:"
  - "  - Create_prefix_port_lists: Create prefix and port lists listed in the config."
  - "  - Delete_prefix_port_lists: Delete prefix and port lists listed in the config."
  - "  - Create_prefix_lists: Create prefix lists listed in the config."
  - "  - Delete_prefix_lists: Delete prefix lists listed in the config."
  - "  - Create_port_lists: Create port lists listed in the config."
  - "  - Delete_port_lists: Delete port lists listed in the config."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs."
  - "YAML schema uses CamelCase keys (for example: C(networkLists), C(portLists))."
  - >-
    Create idempotency: compares intended prefix and port lists to existing device state;
    skips push when already matched (V(changed)=V(false)).
  - >-
    On C(create_*) operations, each list entry may use C(state: absent) to remove that name only
    (sends C(list: null)) while other entries in the same file are created or updated. Default is
    C(state: present).
  - "Delete deletes only the prefix and port lists listed in the YAML."
  - >-
    Delete payload uses C(networkLists: null) and C(portLists: null); this module preserves nulls in the final
    payload pushed to the API.
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply would update
    at least one device. Use C(--diff) to preview C(details.diff_plan) and Ansible C(diff).
version_added: "26.5.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  prefix_port_list_config_file:
    description:
      - Path to the prefix and port list YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(networkLists) and C(portLists) (list of devices).
    type: str
    required: true
  operation:
    description:
      - Specific operation to perform.
      - C(create_prefix_port_lists) builds full prefix and port list objects.
      - >-
        C(delete_prefix_port_lists) deletes listed prefix and port lists by setting
        networkLists=null and portLists=null.
      - C(create_prefix_lists) builds full prefix list objects.
      - C(delete_prefix_lists) deletes listed prefix lists by setting networkLists=null.
      - C(create_port_lists) builds full port list objects.
      - C(delete_port_lists) deletes listed port lists by setting portLists=null.
    type: str
    required: false
    choices:
      - create_prefix_port_lists
      - delete_prefix_port_lists
      - create_prefix_lists
      - delete_prefix_lists
      - create_port_lists
      - delete_port_lists
  state:
    description:
      - Desired state for prefix and port lists.
      - >-
        C(present) maps to C(create_prefix_port_lists); C(absent) maps to C(delete_prefix_port_lists),
        C(create_prefix_lists), C(delete_prefix_lists), C(create_port_lists), C(delete_port_lists) if
        operation not set.
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
    description: Supports Ansible's C(--diff) for pending traffic policy list updates.
    support: full
    details: >
      When the playbook runs with C(--diff) and a device would change, the module returns a C(diff)
      dictionary (C(before) / C(after) strings). Structured entries are also in C(details.diff_plan).

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0

author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure prefix and port lists
  graphiant.naas.graphiant_prefix_port_list:
    operation: create_prefix_port_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: present
  register: create_prefix_port_lists_result
  no_log: true

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ prefix_port_list_result.msg }}"

- name: Deconfigure prefix and port lists (deletes only prefixes and port lists listed in YAML)
  graphiant.naas.graphiant_prefix_port_list:
    operation: delete_prefix_port_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: absent
  register: delete_prefix_port_lists_result
  no_log: true

- name: Create prefix lists
  graphiant.naas.graphiant_prefix_port_list:
    operation: create_prefix_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: present
  register: create_prefix_lists_result
  no_log: true

- name: Display create prefix lists result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ create_prefix_lists_result.msg }}"
  no_log: true

- name: Delete prefix lists
  graphiant.naas.graphiant_prefix_port_list:
    operation: delete_prefix_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: absent
  register: delete_prefix_lists_result
  no_log: true

- name: Display delete prefix lists result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ delete_prefix_lists_result.msg }}"
  no_log: true

- name: Create port lists
  graphiant.naas.graphiant_prefix_port_list:
    operation: create_port_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: present
  register: create_port_lists_result
  no_log: true

- name: Display create port lists result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ create_port_lists_result.msg }}"
  no_log: true

- name: Delete port lists
  graphiant.naas.graphiant_prefix_port_list:
    operation: delete_port_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: absent
  register: delete_port_lists_result
  no_log: true

- name: Display delete port lists result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ delete_port_lists_result.msg }}"
  no_log: true
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Prefix and port lists already match desired state; no changes needed"
changed:
  description:
    - Whether the operation made changes.
    - V(true) when config would be pushed to at least one device; V(false) when intended state already matched.
    - In check mode (C(--check)), no configuration is pushed, but V(changed) reflects whether changes would be made.
  type: bool
  returned: always
  sample: false
operation:
  description: The operation performed.
  type: str
  returned: always
  sample: "create_prefix_port_lists"
prefix_port_list_config_file:
  description: The prefix and port list config file used for the operation.
  type: str
  returned: always
  sample: "sample_prefix_and_port_list.yaml"
configured_devices:
  description: Device names where configuration was pushed (when changed=true).
  type: list
  elements: str
  returned: when supported
  sample: ["edge-1-sdktest"]
skipped_devices:
  description: Device names that were skipped because desired state already matched.
  type: list
  elements: str
  returned: when supported
  sample: ["edge-1-sdktest"]
details:
  description: Raw manager result details (includes C(diff_plan), configured/skipped device lists).
  type: dict
  returned: when supported
diff:
  description: Ansible diff output when the playbook runs with C(--diff) and at least one device would change.
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
                f"graphiant_prefix_port_list: manager {name!s} failed: {type(e).__name__}: {e!s}",
            )
        raise
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []

        if changed:
            msg = success_msg
        else:
            # Make "ok/no-change" messaging explicit and useful.
            msg = no_change_msg
            if skipped:
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
        prefix_port_list_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=[
                "create_prefix_port_lists",
                "delete_prefix_port_lists",
                "create_prefix_lists",
                "delete_prefix_lists",
                "create_port_lists",
                "delete_port_lists",
            ],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["prefix_port_list_config_file"]

    if not operation:
        operation = "create_prefix_port_lists" if state == "present" else "delete_prefix_port_lists"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_prefix_port_list: start operation={operation!r} "
                    f"prefix_port_list_config_file={cfg_file!r} check_mode={module.check_mode!r}"
                ),
            )
        # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                "graphiant_prefix_port_list: GraphiantConfig obtained; dispatching to prefix_port_list manager",
            )

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "create_prefix_port_lists":
            result = execute_with_logging(
                module,
                graphiant_config.prefix_port_list.create_prefix_port_lists,
                cfg_file,
                success_msg="Successfully created prefix and port lists",
                no_change_msg="Prefix and Port lists already match desired state; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        elif operation == "delete_prefix_port_lists":
            result = execute_with_logging(
                module,
                graphiant_config.prefix_port_list.delete_prefix_port_lists,
                cfg_file,
                success_msg="Successfully deleted prefix and port lists",
                no_change_msg="Prefix and Port lists already absent (or already removed); no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        elif operation == "create_prefix_lists":
            result = execute_with_logging(
                module,
                graphiant_config.prefix_port_list.create_prefix_lists,
                cfg_file,
                success_msg="Successfully created prefix lists",
                no_change_msg="Prefix lists already match desired state; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        elif operation == "delete_prefix_lists":
            result = execute_with_logging(
                module,
                graphiant_config.prefix_port_list.delete_prefix_lists,
                cfg_file,
                success_msg="Successfully deleted prefix lists",
                no_change_msg="Prefix lists already absent (or already removed); no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        elif operation == "create_port_lists":
            result = execute_with_logging(
                module,
                graphiant_config.prefix_port_list.create_port_lists,
                cfg_file,
                success_msg="Successfully created port lists",
                no_change_msg="Port lists already match desired state; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        elif operation == "delete_port_lists":
            result = execute_with_logging(
                module,
                graphiant_config.prefix_port_list.delete_port_lists,
                cfg_file,
                success_msg="Successfully deleted port lists",
                no_change_msg="Port lists already absent (or already removed); no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        else:
            supported_ops = (
                "create_prefix_port_lists, delete_prefix_port_lists, create_prefix_lists, "
                "delete_prefix_lists, create_port_lists, delete_port_lists"
            )
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. Supported operations: {supported_ops}.",
                operation=operation,
            )
            return

        if params.get("detailed_logs"):
            preview = result_msg if len(result_msg) <= 200 else (result_msg[:200] + "…")
            ansible_module_log(
                module,
                f"graphiant_prefix_port_list: success changed={changed!r} result_msg_preview={preview!r}",
            )
        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            prefix_port_list_config_file=cfg_file,
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
                f"graphiant_prefix_port_list: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_prefix_port_list: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
