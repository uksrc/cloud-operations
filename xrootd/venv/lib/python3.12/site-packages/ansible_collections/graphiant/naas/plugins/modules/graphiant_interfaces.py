#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant interfaces and circuits.

This module provides comprehensive interface management capabilities including:
- LAN interface configuration and deconfiguration
- WAN interface and circuit management
- Circuit-only operations (for static routes)
- Combined interface operations
"""

DOCUMENTATION = r"""
---
module: graphiant_interfaces
short_description: Manage Graphiant interfaces and circuits
description:
  - This module provides comprehensive interface and circuit management capabilities for Graphiant Edge devices.
  - Supports LAN interface configuration and deconfiguration for subinterfaces.
  - Enables WAN interface and circuit management with static routes.
  - Supports circuit-only operations for updating static routes without reconfiguring interfaces.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.12.0"
notes:
  - "Interface Operations:"
  - "  - LAN interfaces: Configure/deconfigure subinterfaces for LAN connectivity."
  - "  - WAN interfaces: Configure/deconfigure WAN circuits and interfaces together."
  - "  - Circuits only: Update circuit configurations including static routes without touching interfaces."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs and validates configurations."
  - "Deconfigure operations are idempotent and safe to run multiple times."
  - >-
    Configure operations always push the desired config (they may report changed even if the device
    is already configured).
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
  - >-
    LAN segment move: When an interface or subinterface is moved to a different LAN segment, the
    API requires a two-step push (segment-only then full config). The module does this
    automatically; in check mode both payloads are shown.
  - "WAN static-route cleanup (important):"
  - "  - Detaching a WAN interface from a circuit may be treated by the backend as a circuit removal."
  - "    If that circuit still has static routes, the operation can fail with:"
  - "    'error removing circuit \"<name>\". Remove static routes first.'"
  - >-
    V(deconfigure_wan_circuits_interfaces) and V(deconfigure_interfaces) automatically remove static
    routes first (when a circuit config is provided).
  - "  - Use V(deconfigure_circuits) when you only want to remove static routes and keep interfaces/circuits attached."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  interface_config_file:
    description:
      - Path to the interface configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain interface definitions with device names, interface names, and subinterface configurations.
    type: str
    required: true
  circuit_config_file:
    description:
      - Path to the circuit configuration YAML file.
      - >-
        Required for WAN and circuit operations (V(configure_wan_circuits_interfaces),
        V(deconfigure_wan_circuits_interfaces), V(configure_circuits), V(deconfigure_circuits)).
      - Optional for LAN-only operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain circuit definitions with static routes and circuit configurations.
    type: str
    required: false
  operation:
    description:
      - "The specific interface operation to perform."
      - "V(configure_interfaces): Configure all interfaces (LAN and WAN) in one operation."
      - >-
        V(deconfigure_interfaces): Deconfigure all interfaces. Removes WAN static routes first (when
        circuit config provided), then resets parent interface to default LAN and deletes
        subinterfaces.
      - "V(configure_lan_interfaces): Configure LAN interfaces (subinterfaces) only."
      - "V(deconfigure_lan_interfaces): Deconfigure LAN interfaces (subinterfaces) only."
      - "V(configure_wan_circuits_interfaces): Configure WAN circuits and interfaces together."
      - >-
        V(deconfigure_wan_circuits_interfaces): Deconfigure WAN circuits and interfaces together
        (two-stage: static routes first, then interface reset).
      - "V(configure_circuits): Configure circuits only. Can be called separately after interface is configured."
      - "V(deconfigure_circuits): Deconfigure circuits only. Removes static routes if any."
    type: str
    choices:
      - configure_interfaces
      - deconfigure_interfaces
      - configure_lan_interfaces
      - deconfigure_lan_interfaces
      - configure_wan_circuits_interfaces
      - deconfigure_wan_circuits_interfaces
      - configure_circuits
      - deconfigure_circuits
  state:
    description:
      - "The desired state of the interfaces."
      - "V(present): Maps to V(configure_interfaces) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure_interfaces) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  circuits_only:
    description:
      - If V(true), perform a circuits-only deconfigure (static route removal) and skip interface changes.
      - Supported for V(deconfigure_interfaces) and V(deconfigure_wan_circuits_interfaces).
      - When V(true), static routes are removed from referenced circuits, but interfaces remain configured.
    type: bool
    default: false
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all interface operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: >
      Supports check mode. In check mode, no configuration is pushed to the devices but payloads
      that would be pushed are logged with C([check_mode]).
    support: full
    details: >
      When run with C(--check), the module logs the exact payloads that would be pushed with a
      C([check_mode]) prefix so you can see what configuration would be applied.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0

seealso:
  - module: graphiant.naas.graphiant_global_config
    description: >
      Configure global objects (LAN segments, VPN profiles) that may be referenced
      in interface configurations.
  - module: graphiant.naas.graphiant_bgp
    description: Configure BGP peering after interfaces are configured

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure all interfaces (LAN and WAN)
  graphiant.naas.graphiant_interfaces:
    operation: configure_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: configure_result

- name: Configure LAN interfaces only
  graphiant.naas.graphiant_interfaces:
    operation: configure_lan_interfaces
    interface_config_file: "sample_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure WAN circuits and interfaces
  graphiant.naas.graphiant_interfaces:
    operation: configure_wan_circuits_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure circuits only (update static routes)
  graphiant.naas.graphiant_interfaces:
    operation: configure_circuits
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure circuits (remove static routes)
  graphiant.naas.graphiant_interfaces:
    operation: deconfigure_circuits
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure WAN circuits and interfaces
  graphiant.naas.graphiant_interfaces:
    operation: deconfigure_wan_circuits_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure all interfaces
  graphiant.naas.graphiant_interfaces:
    operation: deconfigure_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure interfaces using state parameter
  graphiant.naas.graphiant_interfaces:
    state: absent
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
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
  sample: "Successfully configured all interfaces"
changed:
  description:
    - Whether the operation made changes to the system.
    - Configure operations typically return V(true) because the configuration is pushed via PUT.
    - Deconfigure operations may return V(false) when nothing needs to be removed (idempotent).
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - >-
      One of V(configure_interfaces), V(deconfigure_interfaces), V(configure_lan_interfaces),
      V(deconfigure_lan_interfaces), V(configure_wan_circuits_interfaces),
      V(deconfigure_wan_circuits_interfaces), V(configure_circuits), or V(deconfigure_circuits).
  type: str
  returned: always
  sample: "configure_interfaces"
interface_config_file:
  description:
    - The interface configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_interface_config.yaml"
circuit_config_file:
  description:
    - The circuit configuration file used for the operation.
    - Only returned when circuit_config_file was provided.
  type: str
  returned: when applicable
  sample: "sample_circuit_config.yaml"
circuits_only:
  description:
    - Whether only circuits were affected in the operation.
  type: bool
  returned: always
  sample: false
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
    Main function for the Graphiant interfaces module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        interface_config_file=dict(type="str", required=True),
        circuit_config_file=dict(type="str", required=False, default=None),
        operation=dict(
            type="str",
            required=False,
            choices=[
                "configure_interfaces",
                "deconfigure_interfaces",
                "configure_lan_interfaces",
                "deconfigure_lan_interfaces",
                "configure_wan_circuits_interfaces",
                "deconfigure_wan_circuits_interfaces",
                "configure_circuits",
                "deconfigure_circuits",
            ],
        ),
        circuits_only=dict(type="bool", required=False, default=False),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    interface_config_file = params["interface_config_file"]
    circuit_config_file = params.get("circuit_config_file")
    circuits_only = params.get("circuits_only", False)

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = [
            "configure_interfaces",
            "deconfigure_interfaces",
            "configure_lan_interfaces",
            "deconfigure_lan_interfaces",
            "configure_wan_circuits_interfaces",
            "deconfigure_wan_circuits_interfaces",
            "configure_circuits",
            "deconfigure_circuits",
        ]
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
            f"Supported operations: {', '.join(supported_operations)}"
        )

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == "present":
            operation = "configure_interfaces"
        elif state == "absent":
            operation = "deconfigure_interfaces"

    # If operation is specified, it takes precedence over state
    # No additional mapping needed as operation is explicit

    # Validate operation-specific requirements
    circuit_operations = [
        "configure_wan_circuits_interfaces",
        "deconfigure_wan_circuits_interfaces",
        "configure_circuits",
        "deconfigure_circuits",
    ]

    if operation in circuit_operations and not circuit_config_file:
        module.fail_json(msg=f"Operation '{operation}' requires 'circuit_config_file' parameter")

    # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "configure_interfaces":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.configure_interfaces,
                interface_config_file,
                circuit_config_file,
                success_msg="Successfully configured all interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_interfaces":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.deconfigure_interfaces,
                interface_config_file,
                circuit_config_file,
                circuits_only,
                success_msg="Successfully deconfigured all interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_lan_interfaces":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.configure_lan_interfaces,
                interface_config_file,
                success_msg="Successfully configured LAN interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_lan_interfaces":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.deconfigure_lan_interfaces,
                interface_config_file,
                success_msg="Successfully deconfigured LAN interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_wan_circuits_interfaces":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.configure_wan_circuits_interfaces,
                circuit_config_file,
                interface_config_file,
                success_msg="Successfully configured WAN circuits and interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_wan_circuits_interfaces":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.deconfigure_wan_circuits_interfaces,
                interface_config_file,
                circuit_config_file,
                circuits_only,
                success_msg="Successfully deconfigured WAN circuits and interfaces",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_circuits":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.configure_circuits,
                circuit_config_file,
                interface_config_file,
                success_msg="Successfully configured circuits",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_circuits":
            result = execute_with_logging(
                module,
                graphiant_config.interfaces.deconfigure_circuits,
                circuit_config_file,
                interface_config_file,
                success_msg="Successfully deconfigured circuits",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        # Return success
        module.exit_json(
            changed=changed,
            msg=result_msg,
            operation=operation,
            interface_config_file=interface_config_file,
            circuit_config_file=circuit_config_file,
            circuits_only=circuits_only,
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
