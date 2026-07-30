#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for querying Graphiant MACsec monitoring status.
"""

DOCUMENTATION = r"""
---
module: graphiant_macsec_info
short_description: Query MACsec monitoring status on Edge/Gateway devices
description:
  - >-
    Returns MACsec monitoring status per interface from
    C(GET /v2/monitoring/macsec/{device_id}/status).
  - >-
    Status values include C(MACSEC_STATUS_SECURE) and C(MACSEC_STATUS_UNSECURE).
  - Read-only; never modifies device configuration.
version_added: "26.5.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  device:
    description:
      - Portal device hostname for C(get_device_id).
    type: str
    required: true
  interface:
    description:
      - Optional main interface name to filter results (e.g. C(LAG1), C(GigabitEthernet7/0/0)).
    type: str
    required: false
  detailed_logs:
    description: Enable detailed logging in the task result message.
    type: bool
    default: false
attributes:
  check_mode:
    description: Supports check mode (always read-only).
    support: full
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0
seealso:
  - module: graphiant.naas.graphiant_macsec
    description: Configure interface MACsec settings.
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Get MACsec status for all interfaces on a device
  graphiant.naas.graphiant_macsec_info:
    device: "edge-1-sdktest"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: macsec_status

- name: Display MACsec statuses
  ansible.builtin.debug:
    var: macsec_status.macsec_statuses

- name: Get MACsec status for one interface
  graphiant.naas.graphiant_macsec_info:
    device: "edge-1-sdktest"
    interface: LAG1
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: lag_macsec_status
"""

RETURN = r"""
msg:
  description: Human-readable result (includes detailed logs when enabled).
  type: str
  returned: always
device:
  description: Portal device hostname queried.
  type: str
  returned: always
device_id:
  description: Portal device ID.
  type: int
  returned: always
macsec_statuses:
  description: List of MACsec status entries per interface.
  type: list
  elements: dict
  returned: always
  contains:
    interfaceName:
      description: Main interface name.
      type: str
    status:
      description: C(MACSEC_STATUS_SECURE) or C(MACSEC_STATUS_UNSECURE).
      type: str
"""

from typing import Any, Dict  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop("success_msg", "Query completed successfully")
    result = func(*args, **kwargs)
    return {"result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        device=dict(type="str", required=True),
        interface=dict(type="str", required=False, default=None),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    device = (params.get("device") or "").strip()
    interface = (params.get("interface") or "").strip() or None

    if not device:
        module.fail_json(msg="device is required.")
        return

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        result = execute_with_logging(
            module,
            graphiant_config.macsec.get_macsec_status,
            device,
            interface,
            success_msg=f"Retrieved MACsec status for {device}",
        )
        details: Dict[str, Any] = result.get("details") or {}
        module.exit_json(
            changed=False,
            msg=result["result_msg"],
            device=details.get("device", device),
            device_id=details.get("device_id"),
            macsec_statuses=details.get("macsec_statuses") or [],
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, "status")
        module.fail_json(msg=error_msg)


if __name__ == "__main__":
    main()
