#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant VRRP (Virtual Router Redundancy Protocol) configuration.

This module provides VRRP management capabilities including:
- VRRP configuration on main interfaces and subinterfaces
- VRRP deconfiguration (disable)
- VRRP enable (enable existing configurations)
"""

DOCUMENTATION = r"""
---
module: graphiant_vrrp
short_description: Manage Graphiant VRRP (Virtual Router Redundancy Protocol) configuration
description:
  - This module provides comprehensive VRRP management for Graphiant Edge devices.
  - >-
    Supports VRRP configuration, deconfiguration, and enable operations on both main interfaces and
    subinterfaces (VLANs).
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
  - All operations are idempotent - safe to run multiple times without causing errors or unintended changes.
version_added: "26.1.0"
notes:
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
  - "VRRP Operations:"
  - >
    - configure: Configure VRRP groups on interfaces and subinterfaces.
      Creates new VRRP configurations with specified virtual router IDs and IP addresses.
  - >
    - deconfigure: Disable VRRP groups from interfaces and subinterfaces.
      Idempotent - skips if VRRP is already disabled.
  - >
    - enable: Enable existing VRRP configurations. Fails if VRRP doesn't exist.
      Idempotent - skips if already enabled.
  - >
    Configuration files support Jinja2 templating syntax for dynamic
    configuration generation.
  - "The module automatically resolves device names to IDs."
  - "Idempotency Details:"
  - >
    The module queries existing VRRP state before making changes. For deconfigure
    operations, it checks if VRRP is already disabled and skips if so. For enable
    operations, it checks if VRRP is already enabled and skips if so. This ensures
    safe repeated execution without errors.
  - "Interfaces must be configured first before applying VRRP using M(graphiant.naas.graphiant_interfaces) module."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  vrrp_config_file:
    description:
      - Path to the VRRP configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain VRRP definitions with device names, interface names, and VRRP group configurations.
    type: str
    required: true
  operation:
    description:
      - "The specific VRRP operation to perform."
      - "V(configure): Configure VRRP groups on interfaces and subinterfaces."
      - "V(deconfigure): Deconfigure VRRP groups from interfaces and subinterfaces."
      - >-
        V(enable): Enable existing VRRP configurations. Fails if VRRP doesn't exist. Idempotent -
        skips if already enabled.
    type: str
    choices:
      - configure
      - deconfigure
      - enable
  state:
    description:
      - "The desired state of the VRRP configuration."
      - "V(present): Maps to V(configure) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all VRRP operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
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
    description: Configure interfaces before setting up VRRP

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure VRRP on interfaces
  graphiant.naas.graphiant_vrrp:
    operation: configure
    vrrp_config_file: "sample_vrrp_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: vrrp_result

- name: Deconfigure VRRP from interfaces
  graphiant.naas.graphiant_vrrp:
    operation: deconfigure
    vrrp_config_file: "sample_vrrp_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure VRRP using state parameter
  graphiant.naas.graphiant_vrrp:
    state: present
    vrrp_config_file: "sample_vrrp_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure VRRP using state parameter
  graphiant.naas.graphiant_vrrp:
    state: absent
    vrrp_config_file: "sample_vrrp_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Enable existing VRRP configuration
  graphiant.naas.graphiant_vrrp:
    operation: enable
    vrrp_config_file: "sample_vrrp_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured VRRP interfaces"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) when VRRP configuration was applied, enabled, or disabled.
    - V(false) when operation was skipped due to idempotency (e.g., already enabled/disabled).
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(configure), V(deconfigure), or V(enable).
  type: str
  returned: always
  sample: "configure"
vrrp_config_file:
  description:
    - The VRRP configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_vrrp_config.yaml"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import capture_library_logs  # noqa: E402


@capture_library_logs
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
    Main function for the Graphiant VRRP module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        vrrp_config_file=dict(type="str", required=True),
        operation=dict(type="str", required=False, choices=["configure", "deconfigure", "enable"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    vrrp_config_file = params["vrrp_config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = ["configure", "deconfigure", "enable"]
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
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.vrrp_interfaces.configure_vrrp_interfaces,
                vrrp_config_file,
                success_msg="Successfully configured VRRP interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.vrrp_interfaces.deconfigure_vrrp_interfaces,
                vrrp_config_file,
                success_msg="Successfully deconfigured VRRP interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "enable":
            result = execute_with_logging(
                module,
                graphiant_config.vrrp_interfaces.enable_vrrp_interfaces,
                vrrp_config_file,
                success_msg="Successfully enabled VRRP interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        # Return success
        module.exit_json(changed=changed, msg=result_msg, operation=operation, vrrp_config_file=vrrp_config_file)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
