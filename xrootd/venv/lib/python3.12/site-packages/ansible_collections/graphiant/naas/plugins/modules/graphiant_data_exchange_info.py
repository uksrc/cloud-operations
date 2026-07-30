#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for querying Graphiant Data Exchange information.

This module provides query capabilities for Data Exchange:
- Services summary information
- Customers summary information
- Service health monitoring
"""

DOCUMENTATION = r"""
---
module: graphiant_data_exchange_info
short_description: Query Graphiant Data Exchange services, customers, and health information
description:
  - This module provides query capabilities for Graphiant Data Exchange information.
  - Returns summary information about Data Exchange services and customers.
  - Provides service health monitoring information for matched customers.
  - All operations return read-only information and never modify the system.
version_added: "25.12.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
notes:
  - "This is a read-only module that queries information only."
  - "All operations return tabulated output for easy reading."
  - "For service health operations, supports both consumer and provider views."
options:
  query:
    description:
      - "The specific information to query."
      - "V(services_summary): Get summary of all Data Exchange services with tabulated output."
      - "Returns service details including IDs, names, status, role, and matched customers count."
      - "V(customers_summary): Get summary of all Data Exchange customers with tabulated output."
      - "Returns customer details including IDs, names, type, status, and matched services count."
      - "V(service_health): Get service health monitoring information for all matched customers."
      - "Returns tabulated health status including overall health, producer prefix health, and customer prefix health."
      - "Supports both consumer and provider views."
    type: str
    required: true
    choices:
      - services_summary
      - customers_summary
      - service_health
  service_name:
    description:
      - Service name for health monitoring operations.
      - Required for V(service_health) query.
      - Must be an existing Data Exchange service name.
    type: str
  is_provider:
    description:
      - Whether to get provider view for service health monitoring.
      - When V(false), returns health from consumer/customer perspective.
      - When V(true), returns health from service provider perspective.
      - Only applicable to V(service_health) query.
    type: bool
    default: false
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all query operations.
      - Logs are captured and included in the RV(msg) return value for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: Supports check mode (always read-only).
    support: full

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0
  - tabulate

seealso:
  - module: graphiant.naas.graphiant_data_exchange
    description: Manage Data Exchange services, customers, matches, and invitations

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Get Data Exchange services summary
  graphiant.naas.graphiant_data_exchange_info:
    query: services_summary
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: services_summary

- name: Display services summary
  ansible.builtin.debug:
    msg: "{{ services_summary.msg }}"

- name: Get Data Exchange customers summary
  graphiant.naas.graphiant_data_exchange_info:
    query: customers_summary
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: customers_summary

- name: Display customers summary
  ansible.builtin.debug:
    msg: "{{ customers_summary.msg }}"

- name: Get service health (consumer view)
  graphiant.naas.graphiant_data_exchange_info:
    query: service_health
    service_name: "de-service-1"
    is_provider: false
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: service_health

- name: Display service health
  ansible.builtin.debug:
    msg: "{{ service_health.msg }}"

- name: Get service health (provider view)
  graphiant.naas.graphiant_data_exchange_info:
    query: service_health
    service_name: "de-service-1"
    is_provider: true
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: service_health_provider

- name: Display service health (provider view)
  ansible.builtin.debug:
    msg: "{{ service_health_provider.msg }}"
"""

RETURN = r"""
msg:
  description:
    - Result message from the query operation, including detailed logs when O(detailed_logs) is enabled.
    - For summary operations, includes tabulated output for easy reading.
    - For health operations, includes tabulated health status for all matched customers.
  type: str
  returned: always
  sample: |
    Data Exchange Services Summary:
    +------------------+----------------------------------+--------+------+-------------------+
    | Service Name     | Service ID                       | Status | Role | Matched Customers |
    +==================+==================================+========+======+===================+
    | de-service-1     | 12345678-1234-1234-1234-12345678 | Active | Both | 2                 |
    +------------------+----------------------------------+--------+------+-------------------+
result_data:
  description:
    - Result data from the query operation, including structured data for summary and health operations.
    - For summary operations, contains service/customer details with IDs, names, status, and counts.
    - For health operations, contains health metrics for all matched customers.
  type: dict
  returned: always
  sample:
    services:
      - service_id: "12345678-1234-1234-1234-12345678"
        service_name: "de-service-1"
        status: "Active"
        role: "Both"
        matched_customers_count: 2
query:
  description:
    - The query that was performed.
    - One of V(services_summary), V(customers_summary), or V(service_health).
  type: str
  returned: always
  sample: "services_summary"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


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
        dict: Result with 'result_msg' and 'result_data' keys
    """
    # Extract success_msg from kwargs before passing to func
    success_msg = kwargs.pop("success_msg", "Query completed successfully")

    try:
        result = func(*args, **kwargs)

        # If the function returns a dict with 'result_msg' and 'result_data' keys, use them
        if isinstance(result, dict) and "result_msg" in result:
            return {"result_msg": result.get("result_msg", success_msg), "result_data": result.get("result_data", {})}

        # Fallback for functions that return data directly
        return {"result_msg": success_msg, "result_data": result if isinstance(result, dict) else {}}
    except Exception as e:
        raise e


def main():
    """Main function for the Data Exchange info module."""

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        query=dict(type="str", required=True, choices=["services_summary", "customers_summary", "service_health"]),
        service_name=dict(type="str", required=False),
        is_provider=dict(type="bool", default=False),
        detailed_logs=dict(type="bool", default=False),
    )

    # Create module instance
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[("query", "service_health", ["service_name"])],
    )

    # Get parameters
    params = module.params
    query = params.get("query")

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params, check_mode=module.check_mode)

        # Get Graphiant config from connection (same pattern as graphiant_data_exchange module)
        graphiant_config = connection.graphiant_config

        # Execute query based on query type
        result_msg = ""
        result_data = {}

        if query == "services_summary":
            result = execute_with_logging(
                module,
                graphiant_config.data_exchange.get_services_summary,
                success_msg="Successfully retrieved Data Exchange services summary",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        elif query == "customers_summary":
            result = execute_with_logging(
                module,
                graphiant_config.data_exchange.get_customers_summary,
                success_msg="Successfully retrieved Data Exchange customers summary",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        elif query == "service_health":
            service_name = params.get("service_name")
            is_provider = params.get("is_provider", False)

            if not service_name:
                module.fail_json(msg="service_health query requires service_name parameter")

            result = execute_with_logging(
                module,
                graphiant_config.data_exchange.get_service_health,
                service_name,
                is_provider,
                success_msg=f"Successfully retrieved service health for service {service_name}",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        else:
            module.fail_json(
                msg=f"Unsupported query: {query}. "
                f"Supported queries are: services_summary, customers_summary, service_health"
            )

        # Return success (always changed=False for info modules)
        module.exit_json(changed=False, msg=result_msg, query=query, result_data=result_data)

    except Exception as e:
        module.fail_json(msg=f"Error executing query: {str(e)}")


if __name__ == "__main__":
    main()
