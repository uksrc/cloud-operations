#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for pushing raw device configurations to Graphiant devices.

This module provides the ability to push any device configuration that conforms
to the Graphiant API spec directly to multiple devices. Users can capture the
request payload from the Graphiant Portal UI developer tools and use it directly.
"""

DOCUMENTATION = r"""
---
module: graphiant_device_config
short_description: Push raw device configurations to Graphiant devices
description:
  - >-
    This module pushes device configurations directly to Graphiant devices using the
    C(/v1/devices/{device_id}/config) API.
  - Supports Edge, Gateway, and Core device types.
  - Enables pushing any configuration that conforms to the Graphiant API specification.
  - >-
    Users can capture API payloads from the Graphiant Portal UI developer tools and use them
    directly in configuration files.
  - Supports optional user-defined Jinja2 templates for configuration generation.
  - Configuration files support Jinja2 templating syntax for dynamic configuration generation.
  - Provides dry-run validation mode to validate configurations before deployment.
version_added: "25.12.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
notes:
  - "Supported Device Types:"
  - "  - Edge devices: Use 'edge' key in payload"
  - "  - Gateway devices: Use 'edge' key in payload (same as edge)"
  - "  - Core devices: Use 'core' key in payload"
  - "Configuration Approach:"
  - "  - The config file contains device_config entries with device names and their payloads."
  - "  - Payloads are JSON structures conforming to the PUT /v1/devices/{device_id}/config API schema."
  - "  - Users can copy payloads directly from the Graphiant Portal UI developer tools."
  - "  - Configuration files support Jinja2 templating for dynamic value substitution."
  - "Template Support:"
  - "  - Optional user-defined templates can be provided to generate payloads from simplified config data."
  - "  - Templates are rendered with the config file data as context."
  - "  - Built-in templates are NOT used - this is a direct API manager."
  - "Concurrent Execution:"
  - "  - Configurations are pushed to multiple devices concurrently for efficiency."
  - "  - Each device's portal status is verified before configuration push."
options:
  config_file:
    description:
      - Path to the device configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - "File must contain I(device_config) list with entries in the format:"
      - "  device_config:"
      - "    - device-name:"
      - "        payload: |"
      - "          { JSON payload conforming to API spec }"
    type: str
    required: true
  template_file:
    description:
      - Optional path to a user-defined Jinja2 template file.
      - When provided, the template is rendered with config file data as context.
      - The rendered template should produce the final I(device_config) structure.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - "Use this to create reusable templates for common configuration patterns."
    type: str
    required: false
  operation:
    description:
      - The specific device configuration operation to perform.
      - "V(configure): Push device configuration to devices (PUT /v1/devices/{device_id}/config)."
      - "V(show_validated_payload): Dry-run mode that shows the validated payload after SDK model processing."
      - "Validates configuration syntax, resolves device names, and displays what would be pushed to the API."
      - "Unrecognized fields are excluded by SDK models. No changes are made to devices."
    type: str
    choices:
      - configure
      - show_validated_payload
    default: configure
  state:
    description:
      - The desired state of the device configuration.
      - "V(present): Maps to V(configure) operation when O(operation) not specified."
      - "V(absent) state is not supported as device configuration is a PUT operation."
    type: str
    choices: [ present ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all device configuration operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: Supports check mode with partial support.
    support: partial
    details: >
      For V(show_validated_payload) operation, check mode returns V(changed=False) as this is
      a read-only validation operation that makes no changes to the system. For V(configure)
      operation, check mode returns V(changed=True) as the module cannot accurately determine
      whether changes would actually be made without querying the current state via API calls.
      The module does not perform state comparison in check mode for V(configure) operations
      due to API limitations. This means that check mode may report changes even when the
      configuration is already applied.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: >
      Configure interfaces and circuits using template-based approach.
      Use graphiant_device_config for more flexible raw payload configurations.
  - module: graphiant.naas.graphiant_bgp
    description: Configure BGP peering using template-based approach
  - module: graphiant.naas.graphiant_global_config
    description: Configure global objects (LAN segments, VPN profiles, etc.)

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Push device configuration to edge devices
  graphiant.naas.graphiant_device_config:
    operation: configure
    config_file: "sample_device_config_payload.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: config_result

- name: Display configuration result
  ansible.builtin.debug:
    msg: "{{ config_result.msg }}"

- name: Show validated payload (dry-run) before pushing
  graphiant.naas.graphiant_device_config:
    operation: show_validated_payload
    config_file: "sample_device_config_payload.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: preview_result

- name: Display validated payload
  ansible.builtin.debug:
    msg: "{{ preview_result.msg }}"

- name: Push configuration using user-defined template
  graphiant.naas.graphiant_device_config:
    operation: configure
    config_file: "sample_device_config_with_template.yaml"
    template_file: "device_config_template.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: template_result

- name: Configure devices with state parameter
  graphiant.naas.graphiant_device_config:
    state: present
    config_file: "sample_device_config_payload.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

# Example config file (sample_device_config_payload.yaml):
# ---
# device_config:
#   - edge-1-sdktest:
#       payload: |
#         {
#           "edge": {
#             "dns": {
#               "dns": {
#                 "static": {
#                   "primaryIpv4V2": { "address": "8.8.8.8" },
#                   "secondaryIpv4V2": { "address": "8.8.4.4" }
#                 }
#               }
#             },
#             "regionName": "us-west-2 (San Jose)"
#           },
#           "description": "Configure custom DNS and region",
#           "configurationMetadata": { "name": "dns_config_v1" }
#         }
#   - edge-2-sdktest:
#       payload: |
#         {
#           "edge": {
#             "dns": {
#               "dns": {
#                 "static": {
#                   "primaryIpv4V2": { "address": "8.8.8.8" },
#                   "secondaryIpv4V2": { "address": "8.8.4.4" }
#                 }
#               }
#             }
#           },
#           "description": "Configure custom DNS"
#         }
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured 3 device(s)"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) for configure operations.
    - V(false) for show_validated_payload operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - Either V(configure) or V(show_validated_payload).
  type: str
  returned: always
  sample: "configure"
config_file:
  description:
    - The configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_device_config_payload.yaml"
template_file:
  description:
    - The template file used for the operation, if provided.
  type: str
  returned: when applicable
  sample: "device_config_template.yaml"
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
            return {"changed": result["changed"], "result_msg": success_msg, "result_data": result}

        # Fallback for functions that don't return change status
        return {"changed": True, "result_msg": success_msg, "result_data": result}
    except Exception as e:
        raise e


def main():
    """
    Main function for the Graphiant device config module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        config_file=dict(type="str", required=True),
        template_file=dict(type="str", required=False, default=None),
        operation=dict(
            type="str", required=False, default="configure", choices=["configure", "show_validated_payload"]
        ),
        state=dict(type="str", required=False, default="present", choices=["present"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    config_file = params["config_file"]
    template_file = params.get("template_file")

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == "present":
            operation = "configure"

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
                graphiant_config.device_config.configure,
                config_file,
                template_file,
                success_msg=f"Successfully configured devices from {config_file}",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "show_validated_payload":
            result = execute_with_logging(
                module,
                graphiant_config.device_config.show_validated_payload,
                config_file,
                template_file,
                success_msg=f"Successfully previewed device configuration from {config_file}",
            )
            # Preview doesn't make changes
            changed = False
            result_msg = result["result_msg"]

        else:
            module.fail_json(
                msg=f"Unsupported operation: {operation}. "
                f"Supported operations are: configure, show_validated_payload"
            )

        # Return success
        result_dict = dict(changed=changed, msg=result_msg, operation=operation, config_file=config_file)
        if template_file:
            result_dict["template_file"] = template_file

        module.exit_json(**result_dict)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
