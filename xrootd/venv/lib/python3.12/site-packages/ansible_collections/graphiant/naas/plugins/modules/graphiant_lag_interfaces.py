#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant LAG configuration.

This module provides LAG interface management capabilities including:
- Configure LAG on Physical interfaces
- Add/remove LAG members
- Update LACP settings
- Configure LAG subinterfaces
- Delete LAG subinterfaces
- Deconfigure LAG
"""

DOCUMENTATION = r"""
---
module: graphiant_lag_interfaces
short_description: Manage Graphiant LAG (Link Aggregation Group) configuration
description:
  - This module provides comprehensive LAG management for Graphiant Edge and
    Gateway devices.
  - Supports configuring and deconfiguring LAGs, adding/removing LAG members,
    updating LACP settings, and managing LAG subinterfaces (VLANs).
  - All operations use Jinja2 templates for consistent configuration
    deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
  - All operations are idempotent - safe to run multiple times without
    causing errors or unintended changes.
version_added: "26.1.0"
notes:
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
  - "LAG Operations:"
  - >
    - configure: Configure LAG on physical interfaces (and optionally
      subinterfaces). Idempotent - creates new LAGs or updates existing ones.
  - >
    - deconfigure: Delete ALL subinterfaces (if present) and then delete the
      main LAG interface. This is a complete cleanup operation that removes
      everything. Idempotent - skips non-existent LAGs and subinterfaces.
  - >
    - add_lag_members: Add member interfaces to an existing LAG. Idempotent -
      skips members already added.
  - >
    - remove_lag_members: Remove member interfaces from an existing LAG.
      Idempotent - skips members already removed.
  - >
    - update_lacp_configs: Update LACP mode/timer. Idempotent - skips if
      config already matches desired state.
  - >
    - delete_lag_subinterfaces: Delete specified VLAN subinterfaces under the
      LAG. Only deletes subinterfaces listed in the config file. Idempotent -
      skips non-existent LAGs and subinterfaces.
  - >
    Configuration files support Jinja2 templating syntax for dynamic
    configuration generation.
  - "The module automatically resolves device names to IDs."
  - "Idempotency Details:"
  - >
    The module queries existing LAG state before making changes. For configure
    operations, duplicate alias assignments are automatically handled by
    removing the alias from the payload when it matches the existing alias.
    For member operations, existing members are checked and only necessary
    changes are applied. For LACP updates, current mode/timer are compared
    before pushing configuration. For deconfigure, all existing subinterfaces
    are automatically detected and deleted before removing the main LAG.
    For delete_lag_subinterfaces, only specified subinterfaces are deleted. For deconfigure, all existing subinterfaces
    are automatically detected and deleted before removing the main LAG.
    For delete_lag_subinterfaces, only specified subinterfaces are deleted.
  - >
    Member interfaces must exist on the device; interface names in the config
    are resolved to interface IDs via device info.
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  lag_config_file:
    description:
      - Path to the LAG configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved
        using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic
        generation.
      - File must contain LAG definitions with device names, LAG name/alias,
        segment, mtu, ipv4, ipv6, lacpMode, lacpTimer, member interfaces, and
        optional subinterfaces.
    type: str
    required: true
  operation:
    description:
      - "The specific LAG operation to perform."
      - "V(configure): Configure LAG for devices in the config file."
      - >
        "V(deconfigure): Delete ALL subinterfaces (if present) and then delete
        the main LAG interface. Complete cleanup operation."
      - "V(add_lag_members): Add member interfaces to an existing LAG."
      - "V(remove_lag_members): Remove member interfaces from an existing LAG."
      - "V(update_lacp_configs): Update LACP mode/timer."
      - "V(delete_lag_subinterfaces): Delete VLAN subinterfaces under the LAG."
      - "Note: To add/configure LAG subinterfaces, use V(configure) operation with subinterfaces in the config file."
    type: str
    choices:
      - configure
      - deconfigure
      - add_lag_members
      - remove_lag_members
      - update_lacp_configs
      - delete_lag_subinterfaces
  state:
    description:
      - "The desired state of the LAG configuration."
      - "V(present): Maps to V(configure) when O(operation) is not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) is not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all LAG operations.
      - Logs are captured and included in the result_msg for display using
        M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: >
      Supports check mode. In check mode, no configuration is pushed to the devices
      but payloads that would be pushed are logged with C([check_mode]).
    support: full
    details: >
      When run with C(--check), the module logs the exact payloads that would be pushed
      with a C([check_mode]) prefix so you can see what configuration would be applied.
      The module does not perform state comparison, so V(changed) may be V(True) even
      when the configuration is already applied.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Manage LAN/WAN interface and circuit configuration

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure LAG
  graphiant.naas.graphiant_lag_interfaces:
    operation: configure
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: lag_result

- name: Add LAG members
  graphiant.naas.graphiant_lag_interfaces:
    operation: add_lag_members
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Remove LAG members
  graphiant.naas.graphiant_lag_interfaces:
    operation: remove_lag_members
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Update LACP settings
  graphiant.naas.graphiant_lag_interfaces:
    operation: update_lacp_configs
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure LAG subinterfaces (use configure operation with subinterfaces in config)
  graphiant.naas.graphiant_lag_interfaces:
    operation: configure
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Delete LAG subinterfaces
  graphiant.naas.graphiant_lag_interfaces:
    operation: delete_lag_subinterfaces
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure LAG using state parameter
  graphiant.naas.graphiant_lag_interfaces:
    state: absent
    lag_config_file: "sample_lag_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when
      O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured LAG interfaces"
changed:
  description:
    - Whether the operation made changes to the system.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of configure, deconfigure, add_lag_members, remove_lag_members,
      update_lacp_configs, or delete_lag_subinterfaces.
  type: str
  returned: always
  sample: "configure"
lag_config_file:
  description:
    - The LAG configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_lag_interface_config.yaml"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils import (  # noqa: E402
    graphiant_utils,
    logging_decorator,
)


@logging_decorator.capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    """
    Execute a function with optional detailed logging.

    Args:
        module: Ansible module instance
        func: Function to execute
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        dict: Result with 'changed' and 'result_msg' keys
    """
    # Extract success_msg from kwargs before passing to func
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")

    try:
        result = func(*args, **kwargs)

        # If the function returns a dict with 'changed' key, use it
        if isinstance(result, dict) and "changed" in result:
            return {"changed": result["changed"], "result_msg": success_msg, "details": result}

        # Fallback for functions that don't return change status
        return {"changed": True, "result_msg": success_msg}
    except Exception as e:
        raise e


def main():
    """
    Main function for the Graphiant LAG module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_utils.graphiant_portal_auth_argument_spec(),
        lag_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=[
                "configure",
                "deconfigure",
                "add_lag_members",
                "remove_lag_members",
                "update_lacp_configs",
                "delete_lag_subinterfaces",
            ],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    lag_config_file = params["lag_config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = [
            "configure",
            "deconfigure",
            "add_lag_members",
            "remove_lag_members",
            "update_lacp_configs",
            "delete_lag_subinterfaces",
        ]
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
            f"Supported operations: {', '.join(supported_operations)}"
        )

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == "present":
            operation = "configure"
        elif state == "absent":
            operation = "deconfigure"

    # If operation is specified, it takes precedence over state
    # No additional mapping needed as operation is explicit

    # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.

    try:
        # Get Graphiant connection
        connection = graphiant_utils.get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.lag_interfaces.configure,
                lag_config_file,
                success_msg="Successfully configured LAG interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.lag_interfaces.deconfigure,
                lag_config_file,
                success_msg="Successfully deconfigured LAG",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "add_lag_members":
            result = execute_with_logging(
                module,
                graphiant_config.lag_interfaces.add_lag_members,
                lag_config_file,
                success_msg="Successfully added LAG members",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "remove_lag_members":
            result = execute_with_logging(
                module,
                graphiant_config.lag_interfaces.remove_lag_members,
                lag_config_file,
                success_msg="Successfully removed LAG members",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "update_lacp_configs":
            result = execute_with_logging(
                module,
                graphiant_config.lag_interfaces.update_lacp_configs,
                lag_config_file,
                success_msg="Successfully updated LACP configuration",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "delete_lag_subinterfaces":
            result = execute_with_logging(
                module,
                graphiant_config.lag_interfaces.delete_lag_subinterfaces,
                lag_config_file,
                success_msg="Successfully deleted LAG subinterfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        else:
            module.fail_json(
                msg=f"Invalid operation: {operation}",
                operation=operation,
            )

        # Return success
        module.exit_json(changed=changed, msg=result_msg, operation=operation, lag_config_file=lag_config_file)

    except Exception as e:
        error_msg = graphiant_utils.handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
