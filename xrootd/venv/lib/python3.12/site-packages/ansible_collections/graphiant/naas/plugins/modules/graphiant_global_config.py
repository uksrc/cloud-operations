#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant global configuration objects.

This module provides global configuration management capabilities including:
- Prefix sets configuration and deconfiguration
- BGP & Graphiant filters (routing policies) management
- SNMP services management
- Syslog services management
- NTP services management
- IPFIX services management
- VPN profiles management
- LAN segments management
"""

DOCUMENTATION = r"""
---
module: graphiant_global_config
short_description: Manage Graphiant global configuration objects
description:
  - This module provides comprehensive global configuration object management for Graphiant devices.
  - >
    Supports multiple global object types: prefix sets, BGP & Graphiant filters, SNMP services,
    syslog services, NTP services, IPFIX services, VPN profiles, and LAN segments.
  - Can manage all object types together using general operations or specific object types individually.
  - All operations use Jinja2 templates for consistent configuration deployment.
version_added: "25.12.0"
notes:
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
  - "Global Configuration Operations:"
  - "  - General operations (V(configure), V(deconfigure)):
  - Automatically detect and process all configuration types in the YAML file."
  - "  - Specific operations (V(configure_*), V(deconfigure_*)):
  - Process only the specific configuration type."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves names to IDs for sites, LAN segments, and other referenced objects."
  - "All operations are idempotent and safe to run multiple times."
  - "Global objects can be referenced by other modules (BGP, Sites, Data Exchange) after creation."
  - "When both O(operation) and O(state) are provided, O(operation) takes precedence."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  config_file:
    description:
      - Path to the global configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain the appropriate global object definitions based on the operation type.
    type: str
    required: true
  operation:
    description:
      - "The specific global configuration operation to perform."
      - "V(configure): Configure all global objects (automatically detects all types in the file)."
      - "V(deconfigure): Deconfigure all global objects (automatically detects all types in the file)."
      - "V(configure_prefix_sets): Configure global prefix sets only."
      - "V(deconfigure_prefix_sets): Deconfigure global prefix sets only."
      - "V(configure_bgp_filters): Configure global BGP filters (routing policies) only."
      - "V(deconfigure_bgp_filters): Deconfigure global BGP filters only."
      - "V(configure_graphiant_filters): Configure global Graphiant filters (GraphiantIn/GraphiantOut) only."
      - "V(deconfigure_graphiant_filters): Deconfigure global Graphiant filters only."
      - "V(configure_snmp_services): Configure global SNMP services only."
      - "V(deconfigure_snmp_services): Deconfigure global SNMP services only."
      - "V(configure_syslog_services): Configure global syslog services only."
      - "V(deconfigure_syslog_services): Deconfigure global syslog services only."
      - "V(configure_ntps): Configure global NTP objects only."
      - "V(deconfigure_ntps): Deconfigure global NTP objects only."
      - "V(configure_ipfix_services): Configure global IPFIX services only."
      - "V(deconfigure_ipfix_services): Deconfigure global IPFIX services only."
      - "V(configure_vpn_profiles): Configure global VPN profiles only."
      - "V(deconfigure_vpn_profiles): Deconfigure global VPN profiles only."
      - "V(configure_lan_segments): Configure global LAN segments only."
      - "V(deconfigure_lan_segments): Deconfigure global LAN segments only."
      - "V(configure_site_lists): Configure global site lists only."
      - "V(deconfigure_site_lists): Deconfigure global site lists only."
    type: str
    choices:
      - configure
      - deconfigure
      - configure_prefix_sets
      - deconfigure_prefix_sets
      - configure_bgp_filters
      - deconfigure_bgp_filters
      - configure_graphiant_filters
      - deconfigure_graphiant_filters
      - configure_snmp_services
      - deconfigure_snmp_services
      - configure_syslog_services
      - deconfigure_syslog_services
      - configure_ntps
      - deconfigure_ntps
      - configure_ipfix_services
      - deconfigure_ipfix_services
      - configure_vpn_profiles
      - deconfigure_vpn_profiles
      - configure_lan_segments
      - deconfigure_lan_segments
      - configure_site_lists
      - deconfigure_site_lists
  state:
    description:
      - "The desired state of the global configuration objects."
      - "V(present): Maps to V(configure) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all global configuration operations.
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
  - module: graphiant.naas.graphiant_bgp
    description: Attach global BGP filters to BGP peers
  - module: graphiant.naas.graphiant_sites
    description: Attach global objects to sites
  - module: graphiant.naas.graphiant_data_exchange
    description: Use global LAN segments and VPN profiles in Data Exchange workflows

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure all global objects (general operation)
  graphiant.naas.graphiant_global_config:
    operation: configure
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global prefix sets (specific operation)
  graphiant.naas.graphiant_global_config:
    operation: configure_prefix_sets
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global BGP filters
  graphiant.naas.graphiant_global_config:
    operation: configure_bgp_filters
    config_file: "sample_global_bgp_filters.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global Graphiant filters
  graphiant.naas.graphiant_global_config:
    operation: configure_graphiant_filters
    config_file: "sample_global_graphiant_filters.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure global Graphiant filters
  graphiant.naas.graphiant_global_config:
    operation: deconfigure_graphiant_filters
    config_file: "sample_global_graphiant_filters.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global LAN segments
  graphiant.naas.graphiant_global_config:
    operation: configure_lan_segments
    config_file: "sample_global_lan_segments.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global VPN profiles
  graphiant.naas.graphiant_global_config:
    operation: configure_vpn_profiles
    config_file: "sample_global_vpn_profiles.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global NTP objects
  graphiant.naas.graphiant_global_config:
    operation: configure_ntps
    config_file: "sample_global_ntp.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global site lists
  graphiant.naas.graphiant_global_config:
    operation: configure_site_lists
    config_file: "sample_global_site_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure global prefix sets
  graphiant.naas.graphiant_global_config:
    operation: deconfigure_prefix_sets
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure all global objects using state parameter
  graphiant.naas.graphiant_global_config:
    state: absent
    config_file: "sample_global_prefix_lists.yaml"
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
  sample: "Successfully configured all global objects"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) for all configure/deconfigure operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(configure), V(deconfigure), or a specific V(configure_*)/V(deconfigure_*) operation.
  type: str
  returned: always
  sample: "configure_prefix_sets"
config_file:
  description:
    - The configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_global_prefix_lists.yaml"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import capture_library_logs  # noqa: E402


def get_deconfigure_summary(result):
    """
    Extract deleted, skipped, failed (bool), and failed_objects (list) from a deconfigure result.

    result['details'] is either:
    - Single op: { changed, deleted, skipped, failed (bool), failed_objects (list) }
    - Generic:   { changed, details: { routing_policies: {...}, lan_segments: {...}, ... } }
    """
    details = result.get("details") or {}
    if not isinstance(details, dict):
        return {"deleted": [], "skipped": [], "failed": False, "failed_objects": []}
    # failed_objects must be a list; 'failed' key is bool in both top-level and sub-results
    failed_objects = list(details.get("failed_objects") or [])
    out = {
        "deleted": list(details.get("deleted") or []),
        "skipped": list(details.get("skipped") or []),
        "failed_objects": failed_objects,
        "failed": bool(failed_objects),
    }
    if list(details.get("deleted") or []) or list(details.get("skipped") or []) or failed_objects:
        return out  # Single-op: details had the lists
    out = {"deleted": [], "skipped": [], "failed_objects": [], "failed": False}
    for v in details.values():
        if not isinstance(v, dict):
            continue
        for sub in v.values():
            if isinstance(sub, dict):
                out["deleted"].extend(sub.get("deleted") or [])
                out["skipped"].extend(sub.get("skipped") or [])
                out["failed_objects"].extend(sub.get("failed_objects") or [])
    out["failed"] = bool(out["failed_objects"])
    return out


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
    Main function for the Graphiant global configuration module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=[
                "configure",
                "deconfigure",
                "configure_prefix_sets",
                "deconfigure_prefix_sets",
                "configure_bgp_filters",
                "deconfigure_bgp_filters",
                "configure_graphiant_filters",
                "deconfigure_graphiant_filters",
                "configure_snmp_services",
                "deconfigure_snmp_services",
                "configure_syslog_services",
                "deconfigure_syslog_services",
                "configure_ntps",
                "deconfigure_ntps",
                "configure_ipfix_services",
                "deconfigure_ipfix_services",
                "configure_vpn_profiles",
                "deconfigure_vpn_profiles",
                "configure_lan_segments",
                "deconfigure_lan_segments",
                "configure_site_lists",
                "deconfigure_site_lists",
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
    config_file = params["config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = [
            "configure",
            "deconfigure",
            "configure_prefix_sets",
            "deconfigure_prefix_sets",
            "configure_bgp_filters",
            "deconfigure_bgp_filters",
            "configure_graphiant_filters",
            "deconfigure_graphiant_filters",
            "configure_snmp_services",
            "deconfigure_snmp_services",
            "configure_syslog_services",
            "deconfigure_syslog_services",
            "configure_ntps",
            "deconfigure_ntps",
            "configure_ipfix_services",
            "deconfigure_ipfix_services",
            "configure_vpn_profiles",
            "deconfigure_vpn_profiles",
            "configure_lan_segments",
            "deconfigure_lan_segments",
            "configure_site_lists",
            "deconfigure_site_lists",
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
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure,
                config_file,
                success_msg="Successfully configured all global objects",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure,
                config_file,
                success_msg="Successfully deconfigured all global objects",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_prefix_sets":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_prefix_sets,
                config_file,
                success_msg="Successfully configured global prefix sets",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_prefix_sets":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_prefix_sets,
                config_file,
                success_msg="Successfully deconfigured global prefix sets",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_bgp_filters":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_bgp_filters,
                config_file,
                success_msg="Successfully configured global BGP filters",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_bgp_filters":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_bgp_filters,
                config_file,
                success_msg="Successfully deconfigured global BGP filters",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_graphiant_filters":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_graphiant_filters,
                config_file,
                success_msg="Successfully configured global Graphiant filters",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_graphiant_filters":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_graphiant_filters,
                config_file,
                success_msg="Successfully deconfigured global Graphiant filters",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_snmp_services":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_snmp_services,
                config_file,
                success_msg="Successfully configured global SNMP services",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_snmp_services":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_snmp_services,
                config_file,
                success_msg="Successfully deconfigured global SNMP services",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_syslog_services":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_syslog_services,
                config_file,
                success_msg="Successfully configured global syslog services",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_syslog_services":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_syslog_services,
                config_file,
                success_msg="Successfully deconfigured global syslog services",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_ntps":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_ntps,
                config_file,
                success_msg="Successfully configured global NTP objects",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_ntps":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_ntps,
                config_file,
                success_msg="Successfully deconfigured global NTP objects",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_ipfix_services":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_ipfix_services,
                config_file,
                success_msg="Successfully configured global IPFIX services",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_ipfix_services":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_ipfix_services,
                config_file,
                success_msg="Successfully deconfigured global IPFIX services",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_vpn_profiles":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_vpn_profiles,
                config_file,
                success_msg="Successfully configured global VPN profiles",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_vpn_profiles":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_vpn_profiles,
                config_file,
                success_msg="Successfully deconfigured global VPN profiles",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_lan_segments":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_lan_segments,
                config_file,
                success_msg="Successfully configured global LAN segments",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_lan_segments":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_lan_segments,
                config_file,
                success_msg="Successfully deconfigured global LAN segments",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_site_lists":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.configure_site_lists,
                config_file,
                success_msg="Successfully configured global site lists",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_site_lists":
            result = execute_with_logging(
                module,
                graphiant_config.global_config.deconfigure_site_lists,
                config_file,
                success_msg="Successfully deconfigured global site lists",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        # Deconfigure: fail task if any objects could not be deleted (in use); report deleted/skipped/failed
        if operation.startswith("deconfigure"):
            summary = get_deconfigure_summary(result)
            if summary["failed"]:
                parts = []
                if module.check_mode:
                    parts.append("[check_mode]")
                if summary["deleted"]:
                    parts.append("Deleted: %s" % summary["deleted"])
                if summary["skipped"]:
                    parts.append("Skipped: %s" % summary["skipped"])
                parts.append("Failed (in use): %s. Remove from devices or policies first." % summary["failed_objects"])
                module.fail_json(
                    msg=" ".join(parts),
                    deleted=summary["deleted"],
                    skipped=summary["skipped"],
                    failed=True,
                    failed_objects=summary["failed_objects"],
                    changed=changed or bool(summary["deleted"]),
                    operation=operation,
                    config_file=config_file,
                )

        # Return success
        module.exit_json(changed=changed, msg=result_msg, operation=operation, config_file=config_file)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
