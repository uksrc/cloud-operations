#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for Graphiant edge services (DHCP, DNS, LLDP, local web server password).
"""

DOCUMENTATION = r"""
---
module: graphiant_edge_services
short_description: Configure edge services (DHCP, DNS, LLDP, DPI, LWS password)
description:
  - >-
    Configures Edge Services on the Edge/Gateway devices
    C(PUT /v1/devices/{device_id}/config): LAN segment C(dhcpSubnets), device
    C(localWebServerPassword), LAN interface C(lldpEnabled), edge C(dns) mode
    (C(DNSModeStatic), C(DNSModeCloudflare), or C(DNSModeDynamic)), and edge
    C(trafficPolicy.dpiApplications).
  - >-
    Edge/Gateway only; core devices are rejected. Complements M(graphiant.naas.graphiant_global_config)
    (syslog, IPFIX, SNMP) and M(graphiant.naas.graphiant_ntp) (NTP). For unstructured payloads,
    M(graphiant.naas.graphiant_device_config) can push raw edge branch JSON instead.
  - >-
    Supply C(edge_services_config_file) for a bulk C(edge_services) list, and/or C(device) with
    service fields to run a single device or override one device from the file.
  - >-
    DHCP subnet keys in the API combine interface name and C(ipPrefix) with a hyphen. Remove a subnet with
    C(state: absent) in YAML (sends C(subnet: null)). Static lease IPs must not fall inside
    configured DHCP ranges.
  - >-
    Local web server passwords are hashed in GET responses; the module cannot compare plaintext
    to the portal. Diff output uses C(localWebServerPasswordConfigured) booleans. Without
    C(localWebServerPasswordForce) (default), C(localWebServerPassword) is pushed only when the
    device has none configured; if a hash already exists, LWS is skipped. Set
    C(localWebServerPasswordForce) to push when one is already configured.
    If C(localWebServerPasswordForce) is true, C(localWebServerPassword) must be supplied via YAML,
    C(vault_devices_lws_password) (matching device key), or module parameters—the task fails otherwise.
    Clear force after a successful rotate (portal hash makes force non-idempotent).
    Supply passwords via C(localWebServerPassword) in YAML (dev/local; do not commit secrets),
    C(vault_devices_lws_password) (Ansible Vault; recommended), or module parameters.
    Precedence is YAML C(localWebServerPassword) over C(vault_devices_lws_password).
    Config files support self-contained Jinja2 (for loops, set blocks); playbook/Ansible
    variables are not available at render time—pass vault dicts via the module parameter after
    C(include_vars).
  - Idempotent merge for DNS mode, LLDP, and DHCP fields. Configure-only (no deconfigure operation).
  - >-
    Module parameters use camelCase names aligned with the API (C(dhcpSubnets), C(dpiApplications),
    C(localWebServerPassword), C(localWebServerPasswordForce)). Legacy snake_case aliases
    (C(dhcp_subnets), C(dpi_applications), etc.) are still accepted.
  - >-
    DPI applications are pushed under C(edge.trafficPolicy.dpiApplications) as a map keyed by application
    name. The map key is used as C(application.name) in the PUT payload when C(name) is omitted in YAML.
    Each value wraps C(application) fields (C(ipProtocol), networks, ports, and optional references
    to C(sourceNetworkList), C(destinationNetworkList), C(sourcePortList), C(destinationPortList) names
    defined under C(edge.trafficPolicy) via M(graphiant.naas.graphiant_prefix_port_list)). Use
    C(state: absent) on a map entry to remove an application (sends C(application: null)).
    Idempotency compares non-null fields present in YAML; omitted keys and explicit C(null) are
    ignored (the portal does not clear nested match fields via null). Portal-only fields such as
    C(description) are ignored unless set in YAML.
notes:
  - "Configuration files support Jinja2 templating syntax for dynamic value substitution."
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply
    would update at least one device. Use C(--diff) to preview C(details.diff_plan) and Ansible C(diff).
version_added: "26.5.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  edge_services_config_file:
    description:
      - Path to YAML (optional if C(device) is set with at least one service field).
      - Relative paths resolve using the collection config path (see C(GRAPHIANT_CONFIGS_PATH)).
      - Top-level key C(edge_services) is a list of dicts; each dict has one key, the portal device name.
    type: str
    required: false
    aliases:
      - edge_services_file
  device:
    description:
      - Portal device hostname for C(get_device_id). With C(edge_services_config_file), optional overrides.
      - Required when C(edge_services_config_file) is omitted (single-device mode).
    type: str
    required: false
  localWebServerPassword:
    description:
      - Plaintext local web server password (API C(localWebServerPassword)). At least 8 characters with
        upper, lower, and digit. Use C(no_log) in playbooks.
      - May be set in C(edge_services_config_file) YAML per device (without vault) or as a module
        parameter. Takes precedence over C(vault_devices_lws_password) for the same device.
      - Without C(localWebServerPasswordForce), applied only when the device has no password yet;
        skipped silently if one is already configured (portal hash).
    type: str
    required: false
    aliases:
      - local_web_server_password
  localWebServerPasswordForce:
    description:
      - When C(true), push C(localWebServerPassword) even if the device already has a configured
        password. When C(false) or omitted (default), password is pushed only on first set.
      - Requires C(localWebServerPassword) in YAML, C(vault_devices_lws_password), or module parameters;
        the task fails if force is true and no password is available for that device.
    type: bool
    default: false
    aliases:
      - local_web_server_password_force
  dns:
    description:
      - Edge DNS settings. C(mode) is C(DNSModeStatic), C(DNSModeCloudflare), or C(DNSModeDynamic).
      - For static mode, set C(static) with C(primaryIpv4), C(primaryIpv6), C(secondaryIpv4), C(secondaryIpv6).
    type: dict
    required: false
  lldp:
    description:
      - Map of LAN interface names to C(lldpEnabled) boolean.
      - The task fails if a key names a WAN/circuit interface or an interface that does not exist on the device.
    type: dict
    required: false
  dhcpSubnets:
    description:
      - List of DHCP subnet entries (segment, interface, ipPrefix, subnet dict, optional C(state)).
      - >-
        Each C(segment) must match an existing LAN segment on the device. C(interface) and C(ipPrefix)
        must match a configured LAN interface or subinterface. The task fails with a clear error otherwise.
      - >-
        API subnet key is interface name and C(ipPrefix) joined with a hyphen. Use C(state: absent) to remove a subnet.
    type: list
    elements: dict
    required: false
    aliases:
      - dhcp_subnets
  dpiApplications:
    description:
      - >-
        Map of DPI application name to C(application) settings
        (API C(edge.trafficPolicy.dpiApplications)).
      - >-
        The map key is the application name in the API; C(application.name) in YAML is optional and
        defaults to the key. If set, it must match the key. C(ipProtocol) (C(any), C(icmp), C(tcp), or C(udp))
        and optional network/port fields or list name references are required per app.
      - >-
        Use C(state: absent) on an entry to remove an application. Legacy list-of-C(application) YAML is
        also accepted and normalized to this map shape.
    type: dict
    required: false
    aliases:
      - dpi_applications
  vault_devices_lws_password:
    description:
      - >-
        Map of portal device hostname to local web server password (from Ansible Vault via
        C(include_vars)). Keys must match device names in C(edge_services_config_file) or C(device).
        Injected as C(localWebServerPassword) before apply when YAML does not already set
        C(localWebServerPassword) for that device. YAML may set C(localWebServerPasswordForce).
      - >-
        Do not reference Ansible/playbook variables inside the config file; pass this dict as this
        module parameter after C(include_vars). Self-contained Jinja2 in the config file is supported.
    type: dict
    required: false
    default: {}
  operation:
    description: Only C(configure) is supported.
    type: str
    required: false
    default: configure
    choices: [ configure ]
  state:
    description: Only C(present) is supported.
    type: str
    required: false
    default: present
    choices: [ present ]
  detailed_logs:
    description: Enable detailed logging in the task result message.
    type: bool
    default: false
attributes:
  check_mode:
    description: Supports check mode similarly to other device config modules.
    support: full
    details: >
      In check mode, no configuration is pushed; the module still reads current device state to
      determine whether changes would be made. Payloads that would be pushed are logged with a
      C([check_mode]) prefix by the underlying client.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending edge branch updates.
    support: full
    details: >
      When the playbook runs with C(--diff) and a device branch would change, the module returns
      a C(diff) dictionary (C(before) / C(after) strings). LWS password values are not shown; use
      C(localWebServerPasswordConfigured). Structured entries are also in C(details.diff_plan).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0
seealso:
  - module: graphiant.naas.graphiant_device_system
    description: Configure device name, region, and site.
  - module: graphiant.naas.graphiant_interfaces
    description: Configure LAN/WAN interfaces before DHCP subnets and LLDP.
  - module: graphiant.naas.graphiant_global_config
    description: Global syslog, IPFIX, and SNMP (not edge DHCP/DNS/LLDP/LWS).
  - module: graphiant.naas.graphiant_ntp
    description: NTP configuration (separate from edge DNS mode).
  - module: graphiant.naas.graphiant_device_config
    description: Push raw device JSON when structured modules are not used.
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure edge services from YAML
  graphiant.naas.graphiant_edge_services:
    operation: configure
    edge_services_config_file: "sample_edge_services.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: edge_result

- name: Enable LLDP on LAN interfaces for one device
  graphiant.naas.graphiant_edge_services:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-10-joule-sj-dr"
    lldp:
      GigabitEthernet4/0/0: true
      GigabitEthernet8/0/0: true
    detailed_logs: true

- name: Set Cloudflare DNS mode
  graphiant.naas.graphiant_edge_services:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-10-joule-sj-dr"
    dns:
      mode: DNSModeCloudflare

- name: Add DHCP pool on a LAN segment
  graphiant.naas.graphiant_edge_services:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-2-sdktest"
    dhcpSubnets:
      - segment: lan-1-test
        interface: GigabitEthernet8/0/0
        ipPrefix: "10.2.11.0/24"
        state: present
        subnet:
          name: Edge-2-lan-1-test-DHCP
          ipGateway: "10.2.11.1"
          ipRangesV2:
            ipRange:
              - start: "10.2.11.100"
                end: "10.2.11.200"
    state: present

- name: Configure edge services from YAML with vault LWS passwords
# Load vault_secrets.yml with M(ansible.builtin.include_vars) first (see edge_services_management.yml).
- name: Apply edge services (LWS passwords from vault_devices_lws_password)
  graphiant.naas.graphiant_edge_services:
    operation: configure
    edge_services_config_file: "sample_edge_services.yaml"
    vault_devices_lws_password: "{{ vault_devices_lws_password | default({}) }}"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  no_log: true
"""

RETURN = r"""
msg:
  description: Human-readable result (includes detailed logs when enabled).
  type: str
  returned: always
changed:
  description: Whether configuration was pushed to at least one device.
  type: bool
  returned: always
operation:
  description: Operation performed (always C(configure)).
  type: str
  returned: always
edge_services_config_file:
  description: Path to the YAML file used, if any.
  type: str
  returned: when provided
configured_devices:
  description: Device names where an update was applied.
  type: list
  elements: str
  returned: when supported
skipped_devices:
  description: Device names skipped because state already matched.
  type: list
  elements: str
  returned: when supported
diff:
  description: Ansible C(--diff) payload when changes would be applied.
  type: dict
  returned: when playbook uses C(--diff) and at least one device branch would change
details:
  description: Structured payload from the manager (device lists, C(diff_plan), etc.).
  type: dict
  returned: always
"""

from typing import Any, Dict  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)

_SERVICE_PARAM_KEYS = (
    "localWebServerPassword",
    "localWebServerPasswordForce",
    "dns",
    "lldp",
    "dhcpSubnets",
    "dpiApplications",
)


def _has_service_params(module_params: Dict[str, Any]) -> bool:
    return any(module_params.get(k) for k in _SERVICE_PARAM_KEYS if k != "localWebServerPasswordForce")


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    no_change_msg = kwargs.pop("no_change_msg", "No changes needed")
    result = func(*args, **kwargs)
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []
        msg = success_msg if changed else no_change_msg
        if not changed and skipped:
            msg += f" ({len(skipped)} device(s) already match desired state)"
        return {
            "changed": changed,
            "result_msg": msg,
            "details": result,
            "configured_devices": configured,
            "skipped_devices": skipped,
        }
    return {"changed": True, "result_msg": success_msg, "details": result}


def _module_params_from_ansible(params: Dict[str, Any]) -> Dict[str, Any]:
    mp: Dict[str, Any] = {"device": (params.get("device") or "").strip() or None}
    if params.get("localWebServerPassword") is not None:
        mp["localWebServerPassword"] = params["localWebServerPassword"]
    if params.get("localWebServerPasswordForce"):
        mp["localWebServerPasswordForce"] = True
    if params.get("dns") is not None:
        mp["dns"] = params["dns"]
    if params.get("lldp") is not None:
        mp["lldp"] = params["lldp"]
    if params.get("dhcpSubnets") is not None:
        mp["dhcpSubnets"] = params["dhcpSubnets"]
    if params.get("dpiApplications") is not None:
        mp["dpiApplications"] = params["dpiApplications"]
    return mp


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        edge_services_config_file=dict(type="str", required=False, default=None, aliases=["edge_services_file"]),
        device=dict(type="str", required=False, default=None),
        localWebServerPassword=dict(
            type="str", required=False, default=None, no_log=True, aliases=["local_web_server_password"]
        ),
        localWebServerPasswordForce=dict(
            type="bool",
            required=False,
            default=False,
            no_log=True,
            aliases=["local_web_server_password_force"],
        ),
        dns=dict(type="dict", required=False, default=None),
        lldp=dict(type="dict", required=False, default=None),
        dhcpSubnets=dict(type="list", required=False, default=None, elements="dict", aliases=["dhcp_subnets"]),
        dpiApplications=dict(type="dict", required=False, default=None, aliases=["dpi_applications"]),
        vault_devices_lws_password=dict(type="dict", required=False, default={}, no_log=True),
        operation=dict(type="str", required=False, default="configure", choices=["configure"]),
        state=dict(type="str", required=False, default="present", choices=["present"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation") or "configure"
    state = params.get("state", "present")
    cfg_file = params.get("edge_services_config_file")
    device = (params.get("device") or "").strip()
    module_params = _module_params_from_ansible(params)

    if state != "present":
        module.fail_json(msg="Only state=present is supported.", operation=operation)
        return

    if not cfg_file and not device:
        module.fail_json(
            msg="Provide edge_services_config_file and/or device (portal device name).",
            operation=operation,
        )
        return

    vault_lws = params.get("vault_devices_lws_password") or {}
    if not isinstance(vault_lws, dict):
        vault_lws = {}

    if not cfg_file and not _has_service_params(module_params):
        vault_pwd = (vault_lws.get(device) or "").strip() if device else ""
        if not vault_pwd:
            module.fail_json(
                msg=(
                    "When edge_services_config_file is omitted, at least one of localWebServerPassword, "
                    "dns, lldp, dhcpSubnets, or dpiApplications is required, or vault_devices_lws_password "
                    "must include the target device."
                ),
                operation=operation,
            )
            return

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.edge_services.configure,
                cfg_file,
                module_params,
                vault_lws,
                success_msg="Successfully applied edge services settings",
                no_change_msg="Edge services already match desired state; no changes needed",
            )
            details = result.get("details") or {}
            if details.get("no_input"):
                module.exit_json(
                    changed=False,
                    msg="No edge_services entries in YAML; nothing to do.",
                    operation=operation,
                    details=details,
                )
                return

            msg = result["result_msg"]
            exit_payload = dict(
                changed=result["changed"],
                msg=msg,
                operation=operation,
                configured_devices=result.get("configured_devices", []),
                skipped_devices=result.get("skipped_devices", []),
                details=details,
            )
            if cfg_file:
                exit_payload["edge_services_config_file"] = cfg_file
            apply_module_diff(module, exit_payload, details)
            module.exit_json(**exit_payload)
            return

        module.fail_json(msg=f"Unsupported operation: {operation}", operation=operation)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
