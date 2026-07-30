#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for Graphiant device system settings (API name, regionName, site).
"""

DOCUMENTATION = r"""
---
module: graphiant_device_system
short_description: Configure device name, region, and site (Edge or Core)
description:
  - >-
    Sets C(name), C(regionName), and C(site) on the C(edge) or C(core) object for
    C(PUT /v1/devices/{device_id}/config), matching
    U(https://github.com/Graphiant-Inc/graphiant-sdk-python/blob/main/docs/V1DevicesDeviceIdConfigPutRequest.md).
  - >-
    YAML and module options use the same keys as the API branch payload (except optional C(device_type),
    which selects the C(edge) vs C(core) branch and is not sent in the request body).
  - >-
    After C(GET /v1/devices/{id}), the module maps portal C(role) to the config branch
    (C(core) → C(core), C(cpe) → C(edge)) when C(device_type) is omitted. If C(device_type) is set,
    it must match that mapping.
  - >-
    Supply C(system_config_file) for a bulk C(device_system) list, and/or C(device) with
    C(name) / C(regionName) / C(site) to run a single device or to override one device from the file.
  - >-
    Only keys you set are merged onto current device state; omitted keys are left unchanged.
  - Validates portal site exists when C(site.name) is set.
  - >-
    Idempotent when the merged payload already matches the device. Current state is read from
    C(GET /v1/devices/{id}) using C(hostname) as C(name), C(regionOverride.name) when set else
    C(region.name) as C(regionName), and C(site.name) as C(site), aligned with the portal device object.
  - >-
    Omit C(site) entirely to leave the portal site unchanged. A YAML C(site) key with an empty
    value or without C(name) is treated as unspecified (not a request to clear site).
  - >-
    If a device has no site in the portal and your desired config also omits C(site), a config push
    is not attempted, because the API can reject the update. The module fails the task, and
    C(skipped_no_site) lists the affected hostnames. No other device in the same play is updated
    in that run (aborted) until you assign a site in the portal or set C(site) in YAML.
notes:
  - "Deconfigure is not supported; apply desired values with C(operation=configure)."
  - "Configuration files support Jinja2 templating syntax for dynamic value substitution."
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply
    would update at least one device, unless a device fails the no-site rule, in which case the task
    fails and C(changed) is false. Use C(--diff) with check mode to preview branch changes when
    a run would succeed.
version_added: "26.4.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  system_config_file:
    description:
      - Path to YAML (optional if C(device) is set with at least one of C(name), C(regionName), C(site)).
      - Relative paths resolve using the collection config path (see C(GRAPHIANT_CONFIGS_PATH)).
      - Top-level key C(device_system) is a list of dicts; each dict has one key, the portal device name.
    type: str
    required: false
    aliases:
      - device_system_file
  device:
    description:
      - Portal device name for C(get_device_id). With C(system_config_file), optional overrides for this device.
      - Required when C(system_config_file) is omitted (single-device mode).
    type: str
    required: false
  device_type:
    description:
      - Selects the C(edge) or C(core) branch of C(PUT .../config). Not sent in the API body.
      - >-
        Optional. If omitted, the branch is taken from the device's portal C(role) on
        C(GET /v1/devices/{id}) (C(core) for core, C(cpe) for edge/CPE). If set, it must match
        that inferred branch.
    type: str
    required: false
    choices: [ edge, core ]
  name:
    description: Device hostname (API C(edge.name) / C(core.name)).
    type: str
    required: false
  regionName:
    description: Device's region name (API C(regionName)).
    type: str
    required: false
  site:
    description:
      - 'Site object (API C(site)), e.g. C({name: "MySite"}). Must exist in the portal when set.'
    type: dict
    required: false
  operation:
    description: Only C(configure) is supported.
    type: str
    required: false
    default: configure
    choices: [ configure ]
  state:
    description: Only C(present) is supported.
    type: str
    required: false
    default: present
    choices: [ present ]
  detailed_logs:
    description: Enable detailed logging in the task result message.
    type: bool
    default: false
attributes:
  check_mode:
    description: Supports check mode similarly to other device config modules.
    support: full
    details: >
      In check mode, no configuration is pushed; the module still reads current device state to
      determine whether changes would be made. C(changed) is C(true) when at least one device
      would be updated, unless a device hits the no-site error (task fails, C(changed) false). Payloads
      that would be pushed are logged with a C([check_mode]) prefix by the underlying client.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending edge/core branch updates.
    support: full
    details: >
      When the playbook runs with C(--diff) and a device branch would change, the module returns
      a C(diff) dictionary (C(before) / C(after) strings). Structured entries are also in
      C(details.diff_plan).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0
seealso:
  - module: graphiant.naas.graphiant_device_config
    description: Push arbitrary raw device configuration payloads.
  - module: graphiant.naas.graphiant_sites
    description: Create and manage sites referenced in C(site.name).
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure from YAML (device_system list)
  graphiant.naas.graphiant_device_system:
    operation: configure
    system_config_file: "sample_device_system.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: sys_result

- name: Single device from module parameters (branch from portal role if device_type omitted)
  graphiant.naas.graphiant_device_system:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-3-sdktest"
    name: "edge-3-sdktest"
    regionName: "us-east-2 (Atlanta)"
    site:
      name: "New York-sdktest"
    detailed_logs: true

- name: Override site for one device from the file
  graphiant.naas.graphiant_device_system:
    operation: configure
    system_config_file: "sample_device_system.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-3-sdktest"
    site:
      name: "San Jose-sdktest"
"""

RETURN = r"""
msg:
  description: Human-readable result (includes detailed logs when enabled).
  type: str
  returned: always
changed:
  description: Whether configuration was pushed to at least one device.
  type: bool
  returned: always
operation:
  description: Operation performed (always C(configure)).
  type: str
  returned: always
system_config_file:
  description: Path to the YAML file used, if any.
  type: str
  returned: when provided
configured_devices:
  description: Device names where an update was applied.
  type: list
  elements: str
  returned: when supported
skipped_devices:
  description: Device names skipped because state already matched.
  type: list
  elements: str
  returned: when supported
skipped_no_site:
  description: >
    Device names for which a push was not attempted because the portal has no site on the device
    and the desired edge/core payload has no C(site) (the API requires a site before that update).
    The task fails when this is non-empty.
  type: list
  elements: str
  returned: failure
would_configure_devices:
  description: When the task fails for C(skipped_no_site), the other devices that would have been
    updated in the same run but were not, because the batch was aborted.
  type: list
  elements: str
  returned: on failure, when a batch was aborted
aborted_pushes_due_to_no_site:
  description: C(true) when a multi-device run failed for C(skipped_no_site) and other pending updates were not applied.
  type: bool
  returned: on failure, when a batch was aborted
diff:
  description: Ansible C(--diff) payload (C(before) and C(after) text) when changes would be applied.
  type: dict
  returned: when playbook uses C(--diff) and at least one device branch would change
details:
  description: >
    Structured payload from the manager (device lists, C(diff_plan) entries when a branch would change, etc.).
  type: dict
  returned: always
"""

from typing import Any, Dict  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
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
    result = func(*args, **kwargs)
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []
        msg = success_msg if changed else no_change_msg
        if not changed and skipped:
            msg += f" ({len(skipped)} device(s) already match desired state)"
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
        system_config_file=dict(type="str", required=False, default=None, aliases=["device_system_file"]),
        device=dict(type="str", required=False, default=None),
        device_type=dict(type="str", required=False, default=None, choices=["edge", "core"]),
        name=dict(type="str", required=False, default=None),
        regionName=dict(type="str", required=False, default=None),
        site=dict(type="dict", required=False, default=None),
        operation=dict(type="str", required=False, default="configure", choices=["configure"]),
        state=dict(type="str", required=False, default="present", choices=["present"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    # After each module.exit_json() / module.fail_json() below, an explicit return is used so that
    # when the module is unit-tested with a MagicMock (which does not call sys.exit()), control flow
    # does not fall through to a second exit or to "Unsupported operation". In a real Ansible
    # process, exit_json and fail_json terminate the module; the return is unreachable and does
    # not change runtime behavior.

    params = module.params
    operation = params.get("operation") or "configure"
    state = params.get("state", "present")
    cfg_file = params.get("system_config_file")
    device = (params.get("device") or "").strip()

    if state != "present":
        module.fail_json(msg="Only state=present is supported.", operation=operation)
        return

    if not cfg_file and not device:
        module.fail_json(
            msg="Provide system_config_file and/or device (portal device name).",
            operation=operation,
        )
        return

    if not cfg_file:
        if not any(params.get(k) is not None for k in ("name", "regionName", "site")):
            module.fail_json(
                msg="When system_config_file is omitted, at least one of name, regionName, site is required.",
                operation=operation,
            )
            return

    module_params: Dict[str, Any] = {
        "device": device or None,
        "name": params.get("name"),
        "regionName": params.get("regionName"),
        "site": params.get("site"),
    }
    if params.get("device_type") is not None:
        module_params["device_type"] = params["device_type"]

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.device_system.configure,
                cfg_file,
                module_params,
                success_msg="Successfully applied device system settings",
                no_change_msg="Device system settings already match desired state; no changes needed",
            )
            details = result.get("details") or {}
            if details.get("no_input"):
                module.exit_json(
                    changed=False,
                    msg="No device_system entries in YAML; nothing to do.",
                    operation=operation,
                    details=details,
                )
                return

            sns = details.get("skipped_no_site") or []
            if sns:
                wcd = details.get("would_configure_devices") or []
                mod_msg = (
                    f"Cannot apply device system settings: {len(sns)} device(s) have no site in the portal "
                    f"and the desired config has no site (set site: {{name: <site>}} in YAML or assign a site "
                    f"in the portal, then re-run). Affected: {', '.join(sns)}"
                )
                if wcd:
                    mod_msg += f" Other pending update(s) in this run were not applied: {', '.join(wcd)}"
                fail_json_kwargs: Dict[str, Any] = {
                    "msg": mod_msg,
                    "operation": operation,
                    "changed": False,
                    "skipped_no_site": sns,
                    "would_configure_devices": wcd,
                    "skipped_devices": details.get("skipped_devices", []),
                    "configured_devices": details.get("configured_devices", []),
                    "aborted_pushes_due_to_no_site": bool(details.get("aborted_pushes_due_to_no_site", False)),
                    "details": details,
                }
                if cfg_file:
                    fail_json_kwargs["system_config_file"] = cfg_file
                module.fail_json(**fail_json_kwargs)
                return

            msg = result["result_msg"]
            exit_payload = dict(
                changed=result["changed"],
                msg=msg,
                operation=operation,
                configured_devices=result.get("configured_devices", []),
                skipped_devices=result.get("skipped_devices", []),
                details=details,
            )
            if cfg_file:
                exit_payload["system_config_file"] = cfg_file
            apply_module_diff(module, exit_payload, details)
            module.exit_json(**exit_payload)
            return

        module.fail_json(msg=f"Unsupported operation: {operation}", operation=operation)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
