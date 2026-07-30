#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Site-to-Site VPN configuration.

This module provides Site-to-Site VPN management capabilities including:
- Site-to-Site VPN creation on edge devices
- Site-to-Site VPN deletion
"""

DOCUMENTATION = r"""
---
module: graphiant_site_to_site_vpn
short_description: Manage Graphiant Site-to-Site VPN configuration
description:
  - This module provides comprehensive Site-to-Site VPN management for Graphiant Edge devices.
  - Supports Site-to-Site VPN creation and deletion with static or BGP routing.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "26.2.0"
notes:
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
  - "Site-to-Site VPN Operations:"
  - "  - Create: Create Site-to-Site VPN connections on edge devices."
  - "  - Delete: Remove Site-to-Site VPN connections from edge devices."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs."
  - "All operations are idempotent and safe to run multiple times."
  - >-
    Create: The module compares intended config to existing device state (ipsecTunnels). If they
    match, no config is pushed and V(changed) is V(false).
  - >-
    Delete: Only VPNs that exist on the device are removed; a second delete is a no-op and returns
    V(changed) V(false).
  - "Circuits and interfaces must be configured first before applying Site-to-Site VPN."
  - "Vault (create only): O(vault_site_to_site_vpn_keys), O(vault_bgp_md5_passwords)."
  - "Use encrypted I(configs/vault_secrets.yml), I(configs/vault-password-file.sh); no plaintext."
  - "Load with M(ansible.builtin.include_vars) (no_log true); pass dicts so secrets stay in memory."
  - >-
    Vault key must match VPN C(name). See I(configs/vault_secrets.yml.example). Run with
    C(--vault-password-file configs/vault-password-file.sh).
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  site_to_site_vpn_config_file:
    description:
      - Path to the Site-to-Site VPN configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain Site-to-Site VPN definitions with device names and VPN configurations.
    type: str
    required: true
  operation:
    description:
      - "The specific Site-to-Site VPN operation to perform."
      - "V(create): Create Site-to-Site VPN connections on edge devices."
      - "V(delete): Delete Site-to-Site VPN connections from edge devices."
    type: str
    choices:
      - create
      - delete
  state:
    description:
      - "The desired state of the Site-to-Site VPN configuration."
      - "V(present): Maps to V(create) when O(operation) not specified."
      - "V(absent): Maps to V(delete) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all Site-to-Site VPN operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
    type: bool
    default: false
  vault_site_to_site_vpn_keys:
    description:
      - >-
        Dict of VPN name to preshared key (create only). Pass from playbook vars loaded from
        encrypted I(vault_secrets.yml); secrets in memory only.
      - >-
        Key must match the VPN C(name) in the S2S config. Required for create when the config
        defines VPNs that need a preshared key.
    type: dict
    default: {}
    required: false
  vault_bgp_md5_passwords:
    description:
      - >-
        Dict of VPN name to BGP MD5 password (create only). Pass from playbook vars loaded from
        encrypted I(vault_secrets.yml); secrets in memory only.
      - Key must match the VPN C(name) in the config. Optional; BGP VPNs without an entry get no md5Password.
    type: dict
    default: {}
    required: false

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
  diff_mode:
    description: Supports diff mode.
    support: full
    details: >
      With C(--diff), the module shows per-device before/after snapshots of
      C(edge.siteToSiteVpn) (secrets redacted) so you can see exactly which VPN
      tunnels would be created, updated, or deleted.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces before setting up Site-to-Site VPN
  - module: graphiant.naas.graphiant_device_config
    description: Alternative method for device configuration

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
# Playbook: use encrypted configs/vault_secrets.yml (from vault_secrets.yml.example),
# decrypt with configs/vault-password-file.sh (ANSIBLE_VAULT_PASSPHRASE). Run with:
#   ansible-playbook site_to_site_vpn.yml --vault-password-file configs/vault-password-file.sh --tags create

- name: Create Site-to-Site VPN (vault dicts from include_vars; secrets in memory only)
  graphiant.naas.graphiant_site_to_site_vpn:
    operation: create
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    vault_site_to_site_vpn_keys: "{{ vault_site_to_site_vpn_keys | default({}) }}"
    vault_bgp_md5_passwords: "{{ vault_bgp_md5_passwords | default({}) }}"
    detailed_logs: true
  no_log: true
  register: vpn_result

- name: Delete Site-to-Site VPN
  graphiant.naas.graphiant_site_to_site_vpn:
    operation: delete
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Create using state (pass vault dicts when creating)
  graphiant.naas.graphiant_site_to_site_vpn:
    state: present
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    vault_site_to_site_vpn_keys: "{{ vault_site_to_site_vpn_keys | default({}) }}"
    vault_bgp_md5_passwords: "{{ vault_bgp_md5_passwords | default({}) }}"
  no_log: true

- name: Delete using state
  graphiant.naas.graphiant_site_to_site_vpn:
    state: absent
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
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
  sample: "Successfully created Site-to-Site VPN"
changed:
  description:
    - Whether the operation made changes to the system.
    - >-
      V(true) when config was pushed to at least one device; V(false) when intended state already
      matched (create) or no VPNs to delete (delete).
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(create) or V(delete).
  type: str
  returned: always
  sample: "create"
site_to_site_vpn_config_file:
  description:
    - The Site-to-Site VPN configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_site_to_site_vpn.yaml"
diff:
  description: Ansible C(--diff) payload showing per-device before/after Site-to-Site VPN state (secrets redacted).
  type: dict
  returned: when playbook uses C(--diff) and at least one device would be updated
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
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
    Main function for the Graphiant Site-to-Site VPN module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        site_to_site_vpn_config_file=dict(type="str", required=True),
        operation=dict(type="str", required=False, choices=["create", "delete"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
        vault_site_to_site_vpn_keys=dict(type="dict", required=False, default={}, no_log=True),
        vault_bgp_md5_passwords=dict(type="dict", required=False, default={}, no_log=True),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    site_to_site_vpn_config_file = params["site_to_site_vpn_config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = ["create", "delete"]
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
            f"Supported operations: {', '.join(supported_operations)}"
        )

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == "present":
            operation = "create"
        elif state == "absent":
            operation = "delete"

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

        if operation == "create":
            vault_keys = params.get("vault_site_to_site_vpn_keys") or {}
            vault_md5 = params.get("vault_bgp_md5_passwords") or {}
            result = execute_with_logging(
                module,
                graphiant_config.site_to_site_vpn.create_site_to_site_vpn,
                site_to_site_vpn_config_file,
                vault_keys,
                vault_md5,
                success_msg="Successfully created Site-to-Site VPN",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "delete":
            result = execute_with_logging(
                module,
                graphiant_config.site_to_site_vpn.delete_site_to_site_vpn,
                site_to_site_vpn_config_file,
                success_msg="Successfully deleted Site-to-Site VPN",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        # Return success
        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            site_to_site_vpn_config_file=site_to_site_vpn_config_file,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
