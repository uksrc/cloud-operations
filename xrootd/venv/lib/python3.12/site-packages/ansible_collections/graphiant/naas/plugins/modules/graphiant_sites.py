#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant site attachments and detachments.

This module provides site management capabilities including:
- Attaching global system objects to sites
- Detaching global system objects from sites
- Managing site-level configurations
"""

DOCUMENTATION = r"""
---
module: graphiant_sites
short_description: Manage Graphiant sites and object attachments
description:
  - This module provides comprehensive site management capabilities for Graphiant Edge devices.
  - Supports site creation and deletion.
  - Enables attachment and detachment of global system objects to/from sites.
  - Can perform site-only operations or object attachment operations independently.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.12.0"
notes:
  - "Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged with C([check_mode])."
  - "Use playbook I(playbooks/site_management.yml) with tags I(configure_sites), I(deconfigure_sites),"
  - "  I(attach_objects), I(detach_objects), I(configure), I(deconfigure)."
  - "Site Operations:"
  - "  - V(configure): Create sites and attach global objects in one operation."
  - "  - V(deconfigure): Detach global objects and delete sites in one operation."
  - "  - V(configure_sites): Create sites only (without attaching objects)."
  - "  - V(deconfigure_sites): Delete sites only (without detaching objects)."
  - "  - V(attach_objects): Attach global objects to existing sites. Prerequisite: global objects created first."
  - "  - V(detach_objects): Detach global objects from sites (sites remain)."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves site names and global object names to IDs."
  - "All operations are idempotent and safe to run multiple times."
  - "Global objects must be created using M(graphiant.naas.graphiant_global_config) module before attaching to sites."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  site_config_file:
    description:
      - Path to the site configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain site definitions with site names and global object attachments.
    type: str
    required: true
  operation:
    description:
      - "The specific site operation to perform."
      - "V(configure): Create sites and attach global objects in one operation."
      - "V(deconfigure): Detach global objects and delete sites in one operation."
      - "V(configure_sites): Create sites only (without attaching objects)."
      - "V(deconfigure_sites): Delete sites only (without detaching objects)."
      - "V(attach_objects): Attach global objects to existing sites."
      - "V(detach_objects): Detach global objects from sites (without deleting sites)."
    type: str
    choices:
      - configure
      - deconfigure
      - configure_sites
      - deconfigure_sites
      - attach_objects
      - detach_objects
  state:
    description:
      - "The desired state of the sites."
      - "V(present): Maps to V(configure) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all site operations.
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
  - module: graphiant.naas.graphiant_global_config
    description: Configure global objects (LAN segments, prefix sets, etc.) that can be attached to sites
  - module: graphiant.naas.graphiant_data_exchange
    description: Use sites in Data Exchange service configurations

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure sites (create sites and attach objects)
  graphiant.naas.graphiant_sites:
    operation: configure
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: sites_result

- name: Create sites only
  graphiant.naas.graphiant_sites:
    operation: configure_sites
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Attach global objects to existing sites
  graphiant.naas.graphiant_sites:
    operation: attach_objects
    site_config_file: "sample_site_attachments.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Detach global objects from sites
  graphiant.naas.graphiant_sites:
    operation: detach_objects
    site_config_file: "sample_site_attachments.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Delete sites only
  graphiant.naas.graphiant_sites:
    operation: deconfigure_sites
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure sites (detach objects and delete sites)
  graphiant.naas.graphiant_sites:
    operation: deconfigure
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure sites using state parameter
  graphiant.naas.graphiant_sites:
    state: present
    site_config_file: "sample_sites.yaml"
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
  sample: "Successfully configured (created sites and attached objects)"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) for all configure/deconfigure/attach/detach operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - >-
      One of V(configure), V(deconfigure), V(configure_sites), V(deconfigure_sites),
      V(attach_objects), or V(detach_objects).
  type: str
  returned: always
  sample: "configure"
site_config_file:
  description:
    - The site configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_sites.yaml"
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
    Main function for the Graphiant sites module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        site_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=[
                "configure",
                "deconfigure",
                "configure_sites",
                "deconfigure_sites",
                "attach_objects",
                "detach_objects",
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
    site_config_file = params["site_config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = [
            "configure",
            "deconfigure",
            "configure_sites",
            "deconfigure_sites",
            "attach_objects",
            "detach_objects",
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
                graphiant_config.sites.configure,
                site_config_file,
                success_msg="Successfully configured (created sites and attached objects)",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.sites.deconfigure,
                site_config_file,
                success_msg="Successfully deconfigured (detached objects and deleted sites)",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "configure_sites":
            result = execute_with_logging(
                module,
                graphiant_config.sites.configure_sites,
                site_config_file,
                success_msg="Successfully created sites",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation == "deconfigure_sites":
            result = execute_with_logging(
                module,
                graphiant_config.sites.deconfigure_sites,
                site_config_file,
                success_msg="Successfully deleted sites",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation.lower().startswith("attach"):
            result = execute_with_logging(
                module,
                graphiant_config.sites.attach_objects,
                site_config_file,
                success_msg="Successfully attached global system objects to sites",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        elif operation.lower().startswith("detach"):
            result = execute_with_logging(
                module,
                graphiant_config.sites.detach_objects,
                site_config_file,
                success_msg="Successfully detached global system objects from sites",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        # Return success
        module.exit_json(changed=changed, msg=result_msg, operation=operation, site_config_file=site_config_file)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
