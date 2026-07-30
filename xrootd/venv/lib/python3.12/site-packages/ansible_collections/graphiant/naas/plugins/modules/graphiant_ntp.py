#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant device-level NTP objects under:
  edge.ntpGlobalObject
"""

DOCUMENTATION = r"""
---
module: graphiant_ntp
short_description: Manage device-level NTP objects (edge.ntpGlobalObject)
description:
  - Configure or delete device-level NTP objects under C(edge.ntpGlobalObject).
  - Reads a structured YAML config file and builds the raw device-config payload in Python.
  - "Configure is idempotent: compares intended objects to existing device state and skips push when already matched."
  - "Deconfigure deletes only the objects listed in the YAML by setting C(config: null) per object."
notes:
  - "This module manages NTP objects directly on devices (device config API), not the portal-wide global config."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - >-
    Deconfigure payload uses C(config: null) per object; this module preserves nulls in the final
    payload pushed to the API.
version_added: "26.2.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  ntp_config_file:
    description:
      - Path to the NTP YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(ntpGlobalObject) (list of devices).
    type: str
    required: true
  operation:
    description:
      - Specific operation to perform.
      - C(configure) creates/updates NTP objects listed in the config.
      - C(deconfigure) deletes listed NTP objects by setting C(config=null).
    type: str
    required: false
    choices: [ configure, deconfigure ]
  state:
    description:
      - Desired state for NTP objects.
      - C(present) maps to C(configure); C(absent) maps to C(deconfigure) if operation not set.
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
    description: Supports diff mode.
    support: full
    details: >
      With C(--diff), the module shows per-device before/after snapshots of C(edge.ntpGlobalObject)
      so you can see exactly what NTP objects would change.
requirements:
  - python >= 3.7
  - graphiant-sdk >= 25.12.1
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure device-level NTP objects
  graphiant.naas.graphiant_ntp:
    operation: configure
    ntp_config_file: "sample_device_ntp.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: ntp_result
  no_log: true

- name: Deconfigure device-level NTP objects
  graphiant.naas.graphiant_ntp:
    operation: deconfigure
    ntp_config_file: "sample_device_ntp.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

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
ntp_config_file:
  description: The NTP config file used for the operation.
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
diff:
  description: Ansible C(--diff) payload showing per-device before/after NTP state.
  type: dict
  returned: when playbook uses C(--diff) and at least one device would be updated
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
                f"graphiant_ntp: manager {name!s} failed: {type(e).__name__}: {e!s}",
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
        ntp_config_file=dict(type="str", required=True),
        operation=dict(type="str", required=False, choices=["configure", "deconfigure"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["ntp_config_file"]

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_ntp: start operation={operation!r} ntp_config_file={cfg_file!r} "
                    f"check_mode={module.check_mode!r}"
                ),
            )
        # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                "graphiant_ntp: GraphiantConfig obtained; dispatching to NTP manager",
            )

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.ntp.configure,
                cfg_file,
                success_msg="Successfully configured device-level NTP objects",
                no_change_msg="Device-level NTP objects already match desired state; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.ntp.deconfigure,
                cfg_file,
                success_msg="Successfully deconfigured device-level NTP objects",
                no_change_msg="Device-level NTP objects already absent (or already removed); no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        else:
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure.",
                operation=operation,
            )
            return

        if params.get("detailed_logs"):
            preview = result_msg if len(result_msg) <= 200 else (result_msg[:200] + "…")
            ansible_module_log(
                module,
                f"graphiant_ntp: success changed={changed!r} result_msg_preview={preview!r}",
            )
        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            ntp_config_file=cfg_file,
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
                f"graphiant_ntp: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_ntp: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
