#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant BGP peering and routing policies.

This module provides BGP management capabilities including:
- BGP peering configuration and deconfiguration
- Policy attachment and detachment
- Routing policy management
"""

DOCUMENTATION = r"""
---
module: graphiant_bgp
short_description: Manage Graphiant BGP peering and routing policies
description:
  - This module provides comprehensive BGP peering and routing policy management for Graphiant Edge devices.
  - Supports BGP peering neighbor configuration and deconfiguration.
  - Enables attachment and detachment of global BGP routing policies (filters) to BGP peers.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.12.0"
notes:
  - "BGP Operations:"
  - "  - Configure: Create BGP peering neighbors and attach global BGP routing policies."
  - "  - Deconfigure: Remove BGP peering neighbors (policies are automatically detached)."
  - "  - Detach Policies: Detach global BGP routing policies from BGP peers without removing the peers."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names, site names, and policy names to IDs."
  - "All operations are idempotent and safe to run multiple times."
  - "Global BGP filters must be created using M(graphiant.naas.graphiant_global_config) module"
  - "before attaching to BGP peers."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  bgp_config_file:
    description:
      - Path to the BGP configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain BGP peering neighbor definitions with device names, neighbor IPs, and policy references.
    type: str
    required: true
  operation:
    description:
      - "The specific BGP operation to perform."
      - "V(configure): Configure BGP peering neighbors and attach global BGP routing policies."
      - "V(deconfigure): Deconfigure BGP peering neighbors. Policies are automatically detached."
      - "V(detach_policies): Detach global BGP routing policies from BGP peers without removing the peers."
    type: str
    choices:
      - configure
      - deconfigure
      - detach_policies
  state:
    description:
      - "The desired state of the BGP peering."
      - "V(present): Maps to V(configure) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all BGP operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: Supports check mode with partial support.
    support: partial
    details: >
      The module cannot accurately determine whether changes would actually be made without
      querying the current state via API calls. In check mode, the module assumes that changes
      would be made and returns V(changed=True) for all operations (V(configure), V(deconfigure),
      V(detach_policies)). This means that check mode may report changes even when the
      configuration is already applied. The module does not perform state comparison in check
      mode due to API limitations.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces before setting up BGP peering
  - module: graphiant.naas.graphiant_global_config
    description: Configure global BGP filters (routing policies) that can be attached to BGP peers

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure BGP peering and attach policies
  graphiant.naas.graphiant_bgp:
    operation: configure
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: bgp_result

- name: Detach policies from BGP peers
  graphiant.naas.graphiant_bgp:
    operation: detach_policies
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure BGP peering
  graphiant.naas.graphiant_bgp:
    operation: deconfigure
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure BGP peering using state parameter
  graphiant.naas.graphiant_bgp:
    state: present
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure BGP peering using state parameter
  graphiant.naas.graphiant_bgp:
    state: absent
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured BGP peering and attached policies"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) for all configure/deconfigure/detach operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(configure), V(deconfigure), or V(detach_policies).
  type: str
  returned: always
  sample: "configure"
bgp_config_file:
  description:
    - The BGP configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_bgp_peering.yaml"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    get_graphiant_connection,
    graphiant_portal_auth_argument_spec,
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
    Main function for the Graphiant BGP module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        bgp_config_file=dict(type="str", required=True),
        operation=dict(type="str", required=False, choices=["configure", "deconfigure", "detach_policies"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    bgp_config_file = params["bgp_config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = ["configure", "deconfigure", "detach_policies"]
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
                graphiant_config.bgp.configure,
                bgp_config_file,
                success_msg="Successfully configured BGP peering and attached policies",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "detach_policies":
            result = execute_with_logging(
                module,
                graphiant_config.bgp.detach_policies,
                bgp_config_file,
                success_msg="Successfully detached policies from BGP peers",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.bgp.deconfigure,
                bgp_config_file,
                success_msg="Successfully deconfigured BGP peering",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        # Return success
        module.exit_json(changed=changed, msg=result_msg, operation=operation, bgp_config_file=bgp_config_file)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
