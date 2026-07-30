#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Core (backbone) device configuration.

This module provides comprehensive backbone management capabilities including:
- Core interface configuration (loopback, core-to-core links)
- WAN ISP circuit and direct-peer management
- Site and region information configuration
- Per-VRF syslog target management
"""

DOCUMENTATION = r"""
---
module: graphiant_backbone
short_description: Manage Graphiant Core (backbone) device configuration
description:
  - Manage configuration of Graphiant Core (backbone) devices.
  - Supports full Core configuration push as well as targeted operations on core-to-core
    interfaces, core-to-core IPsec tunnels, WAN ISP circuits, direct-peer interfaces,
    and per-VRF syslog targets.
  - All payloads target the V(core) branch of the device configuration (gsdk.put_device_config).
    This is the counterpart to M(graphiant.naas.graphiant_interfaces), which targets the V(edge) branch.
  - The single I(config_yaml_file) holds the full Core configuration; each operation slices the
    appropriate section (interfaces filtered by type / circuit prefix, site block,
    vrfs.syslogTargets, ...) and pushes only that slice.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "26.5.0"
notes:
  - "Operations:"
  - "  - V(configure): Full Core configuration push (name + regionName + site + interfaces + vrfs)."
  - "  - V(deconfigure): Orchestrated full teardown -- runs deconfigure for WAN ISP circuits,
    direct-peer, core-to-core tunnels, core-to-core interfaces, and syslog targets in dependency order."
  - "  - V(configure_core_to_core_interfaces) / V(deconfigure_core_to_core_interfaces): core-to-core
    interfaces on `graphiant-core` (`loopback` / `core_to_core_link` with optional VLAN
    sub-interfaces / `disabled`)."
  - "  - V(configure_core_to_core_tunnel_interfaces) / V(deconfigure_core_to_core_tunnel_interfaces):
    core-to-core IPsec tunnel interfaces (`core_to_core_ipsec_tunnel`)."
  - "  - V(configure_wan_circuits) / V(deconfigure_wan_circuits): ISP transit interfaces with
    circuit names prefixed `isp-` (plus paired `p2mp_tunnel` entries)."
  - "  - V(configure_direct_peer_interfaces) / V(deconfigure_direct_peer_interfaces):
    direct-peer interfaces with circuit names prefixed `direct-peer-`."
  - "  - V(configure_syslog_targets) / V(deconfigure_syslog_targets): per-VRF
    `syslogTargets` blocks under `core.vrfs.<vrf>`."
  - "The module automatically resolves device names to IDs and validates configurations."
  - "Deconfigure operations reset interfaces to the enterprise default LAN (`default-<enterprise_id>`)
    and are idempotent (check device state via `gsdk.get_device_info` before building delete payloads)."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  config_yaml_file:
    description:
      - Path to the backbone (Core) interface configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - >-
        File must contain a top-level `backbone_devices:` list, one entry per Core device with a
        `core:` block (name, regionName, site, interfaces, vrfs).
    type: str
    required: true
  operation:
    description:
      - "The specific backbone operation to perform."
      - "V(configure): Push full Core configuration (name + regionName + site + interfaces + vrfs)."
      - "V(deconfigure): Orchestrated full backbone teardown (WAN circuits, direct-peer,
        core-to-core tunnels, core-to-core interfaces, syslog targets) -- idempotent."
      - "V(configure_core_to_core_interfaces): Configure core-to-core interfaces
        (loopback / core_to_core_link / disabled)."
      - "V(deconfigure_core_to_core_interfaces): Reset core-to-core interfaces to the enterprise default LAN."
      - "V(configure_core_to_core_tunnel_interfaces): Configure core-to-core IPsec tunnel interfaces."
      - "V(deconfigure_core_to_core_tunnel_interfaces): Delete core-to-core IPsec tunnel interfaces."
      - "V(configure_wan_circuits): Configure ISP transit (`isp-*`) interfaces."
      - "V(deconfigure_wan_circuits): Reset ISP transit interfaces."
      - "V(configure_direct_peer_interfaces): Configure direct-peer (`direct-peer-*`) interfaces."
      - "V(deconfigure_direct_peer_interfaces): Reset direct-peer interfaces."
      - "V(configure_syslog_targets): Push per-VRF syslog targets under `core.vrfs.<vrf>`."
      - "V(deconfigure_syslog_targets): Remove per-VRF syslog targets (sets each to null)."
    type: str
    choices:
      - configure
      - deconfigure
      - configure_core_to_core_interfaces
      - deconfigure_core_to_core_interfaces
      - configure_core_to_core_tunnel_interfaces
      - deconfigure_core_to_core_tunnel_interfaces
      - configure_wan_circuits
      - deconfigure_wan_circuits
      - configure_direct_peer_interfaces
      - deconfigure_direct_peer_interfaces
      - configure_syslog_targets
      - deconfigure_syslog_targets
  state:
    description:
      - "The desired state for the Core device configuration."
      - "V(present): Maps to V(configure) when O(operation) is not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) is not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - Logs are captured and included in the result message for display using M(ansible.builtin.debug).
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
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces and circuits on Graphiant Edge devices (counterpart for the V(edge) branch).
  - module: graphiant.naas.graphiant_device_system
    description: Configure `name`, `regionName`, and `site` on Edge or Core devices with full diff.
  - module: graphiant.naas.graphiant_device_config
    description: Push raw device configuration payloads for Edge, Gateway, and Core devices.

author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure all backbone interfaces (full push)
  graphiant.naas.graphiant_backbone:
    operation: configure
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"
    detailed_logs: true

- name: Configure core-to-core interfaces
  graphiant.naas.graphiant_backbone:
    operation: configure_core_to_core_interfaces
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"

- name: Configure core-to-core IPsec tunnels
  graphiant.naas.graphiant_backbone:
    operation: configure_core_to_core_tunnel_interfaces
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"

- name: Configure backbone WAN ISP circuit interfaces
  graphiant.naas.graphiant_backbone:
    operation: configure_wan_circuits
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"

- name: Configure backbone direct-peer interfaces
  graphiant.naas.graphiant_backbone:
    operation: configure_direct_peer_interfaces
    config_yaml_file: "sample_backbone_direct_peer_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"

- name: Configure backbone syslog targets
  graphiant.naas.graphiant_backbone:
    operation: configure_syslog_targets
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"

- name: Deconfigure core-to-core interfaces
  graphiant.naas.graphiant_backbone:
    operation: deconfigure_core_to_core_interfaces
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"

- name: Deconfigure all backbone interfaces (orchestrated teardown)
  graphiant.naas.graphiant_backbone:
    operation: deconfigure
    config_yaml_file: "sample_backbone_config.yaml"
    host: "{{ graphiant_host }}"
    access_token: "{{ graphiant_access_token }}"
    detailed_logs: true
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured backbone (Core) devices"
changed:
  description:
    - Whether the operation pushed configuration changes.
    - V(true) when at least one device's matching configuration was pushed.
    - V(false) when no matching configuration was found in the file.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
  type: str
  returned: always
  sample: "configure"
config_yaml_file:
  description:
    - The interface configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_backbone_config.yaml"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import capture_library_logs  # noqa: E402

SUPPORTED_OPERATIONS = [
    "configure",
    "deconfigure",
    "configure_core_to_core_interfaces",
    "deconfigure_core_to_core_interfaces",
    "configure_core_to_core_tunnel_interfaces",
    "deconfigure_core_to_core_tunnel_interfaces",
    "configure_wan_circuits",
    "deconfigure_wan_circuits",
    "configure_direct_peer_interfaces",
    "deconfigure_direct_peer_interfaces",
    "configure_syslog_targets",
    "deconfigure_syslog_targets",
]


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
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict) and "changed" in result:
            return {"changed": result["changed"], "result_msg": success_msg, "details": result}
        return {"changed": True, "result_msg": success_msg}
    except Exception:
        raise


def main():
    """
    Main function for the Graphiant backbone interfaces module.
    """

    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        config_yaml_file=dict(type="str", required=True),
        operation=dict(type="str", required=False, choices=SUPPORTED_OPERATIONS),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    config_yaml_file = params["config_yaml_file"]

    if not operation and not state:
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
            f"Supported operations: {', '.join(SUPPORTED_OPERATIONS)}"
        )

    # If operation is not specified, fall back to state mapping.
    if not operation:
        if state == "present":
            operation = "configure"
        elif state == "absent":
            operation = "deconfigure"

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        backbone = connection.graphiant_config.backbone

        op_map = {
            "configure": (
                backbone.configure,
                "Successfully configured backbone (Core) devices",
            ),
            "deconfigure": (
                backbone.deconfigure,
                "Successfully deconfigured backbone (Core) devices",
            ),
            "configure_core_to_core_interfaces": (
                backbone.configure_core_to_core_interfaces,
                "Successfully configured core-to-core interfaces",
            ),
            "deconfigure_core_to_core_interfaces": (
                backbone.deconfigure_core_to_core_interfaces,
                "Successfully deconfigured core-to-core interfaces",
            ),
            "configure_core_to_core_tunnel_interfaces": (
                backbone.configure_core_to_core_tunnel_interfaces,
                "Successfully configured core-to-core tunnel interfaces",
            ),
            "deconfigure_core_to_core_tunnel_interfaces": (
                backbone.deconfigure_core_to_core_tunnel_interfaces,
                "Successfully deconfigured core-to-core tunnel interfaces",
            ),
            "configure_wan_circuits": (
                backbone.configure_wan_circuits,
                "Successfully configured backbone WAN ISP circuit interfaces",
            ),
            "deconfigure_wan_circuits": (
                backbone.deconfigure_wan_circuits,
                "Successfully deconfigured backbone WAN ISP circuit interfaces",
            ),
            "configure_direct_peer_interfaces": (
                backbone.configure_direct_peer_interfaces,
                "Successfully configured backbone direct-peer interfaces",
            ),
            "deconfigure_direct_peer_interfaces": (
                backbone.deconfigure_direct_peer_interfaces,
                "Successfully deconfigured backbone direct-peer interfaces",
            ),
            "configure_syslog_targets": (
                backbone.configure_syslog_targets,
                "Successfully configured backbone syslog targets",
            ),
            "deconfigure_syslog_targets": (
                backbone.deconfigure_syslog_targets,
                "Successfully deconfigured backbone syslog targets",
            ),
        }

        if operation not in op_map:
            module.fail_json(msg=f"Unsupported operation '{operation}'", operation=operation)

        func, success_msg = op_map[operation]
        result = execute_with_logging(module, func, config_yaml_file, success_msg=success_msg)

        module.exit_json(
            changed=result["changed"],
            msg=result["result_msg"],
            operation=operation,
            config_yaml_file=config_yaml_file,
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
