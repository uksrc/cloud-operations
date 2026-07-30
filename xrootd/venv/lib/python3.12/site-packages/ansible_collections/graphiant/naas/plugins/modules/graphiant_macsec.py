#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for Graphiant interface MACsec configuration.
"""

DOCUMENTATION = r"""
---
module: graphiant_macsec
short_description: Configure interface MACsec (802.1AE) on Edge/Gateway devices
description:
  - >-
    Configures MACsec on main LAN interfaces (ethernet or LAG) via
    C(PUT /v1/devices/{device_id}/config) under
    C(edge.interfaces.{name}.interface.macsec.macsec) or
    C(edge.lagInterfaces.{name}.interface.macsec.macsec).
  - >-
    Supports enabling/disabling MACsec, configuring encryption enforcement mode,
    key server priority, pre-shared keys (PSK), and SAK profile settings
    (replay protection window and rekey interval).
  - >-
    Supply C(macsec_config_file) for a bulk C(macsec) list, and/or C(device) with
    C(interfaces) to run a single device or override one device from the file.
  - >-
    Add or rotate PSKs with C(presharedKeys) entries (up to 3 per interface). Each key
    requires a unique C(nickname), future C(startTime) (Unix seconds or UTC datetime string
    such as C(2029-12-11 11:12:13)), C(cak), C(ckn),
    and C(cipherSuite) (C(AES_128_CMAC) or C(AES_256_CMAC)). AES-128 requires a
    32-digit hex CAK; AES-256 requires 64-digit hex CAK. C(ckn) is 2–64 hex digits.
  - >-
    Remove a PSK with C(state: absent) on the key entry (sends C(psk: null)). At least
    one PSK must remain when MACsec is enabled.
  - >-
    Existing PSK nicknames cannot be updated in place (CAK, CKN, startTime, cipher suite).
    To rotate, add a new C(presharedKeys) entry with a unique nickname, then remove the old
    key with C(state: absent).
    Listing an unchanged existing key in YAML is idempotent and does not re-push the PSK.
  - >-
    CAK is sensitive. Omit C(cak) from YAML or C(interfaces); set C(ckn) (plaintext) on each
    presharedKeys entry and supply C(vault_devices_macsec_psk) (device → interface → ckn → cak)
    via Ansible Vault. Or set C(cak) in YAML/module params for dev/local only. Diff output
    redacts CAK values and uses C(cakConfigured) booleans.
  - >-
    Idempotent merge per interface field. Partial updates are supported (e.g. C(enabled: false),
    C(keyServerPriority) only, PSK rotation, SAK-only). Configure-only (no deconfigure operation).
  - >-
    Requires a software image with MACsec support on the target device. The API returns
    an error when MACsec is unsupported on the device image.
notes:
  - "Configuration files support Jinja2 templating syntax for dynamic value substitution."
  - >-
    When using C(macsec_config_file), set C(ckn) on each key in YAML, omit C(cak), and pass
    C(vault_devices_macsec_psk) loaded from C(configs/vault_secrets.yml) (see
    C(playbooks/macsec_management.yml)). Plaintext C(cak) in YAML is for dev/local testing only.
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply
    would update at least one device. Use C(--diff) to preview C(details.diff_plan) and Ansible C(diff).
  - >-
    Use M(graphiant.naas.graphiant_macsec_info) to query MACsec monitoring status
    (C(GET /v2/monitoring/macsec/{device_id}/status)).
version_added: "26.5.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  macsec_config_file:
    description:
      - Path to YAML (optional if C(device) is set with C(interfaces)).
      - Relative paths resolve using the collection config path (see C(GRAPHIANT_CONFIGS_PATH)).
      - Top-level key C(macsec) is a list of dicts; each dict has one key, the portal device name.
    type: str
    required: false
    aliases:
      - macsec_file
  device:
    description:
      - Portal device hostname for C(get_device_id). With C(macsec_config_file), optional overrides.
      - Required when C(macsec_config_file) is omitted (single-device mode).
    type: str
    required: false
  interfaces:
    description:
      - Map of main interface name to MACsec settings (ethernet or LAG only; not subinterfaces).
      - Each value may include C(enabled), C(encryptionEnforcementMode), C(keyServerPriority),
        C(presharedKeys), and C(sakConfiguration).
    type: dict
    required: false
  vault_devices_macsec_psk:
    description:
      - >-
        Nested map C(device → interface → ckn → cak) from Ansible Vault via C(include_vars)
        (key C(vault_devices_macsec_psk) in C(configs/vault_secrets.yml)). When YAML or
        C(interfaces) omit C(cak) but include C(ckn), the module looks up CAK by C(ckn).
        Explicit C(cak) in YAML or module params is not overwritten.
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
  diff_mode:
    description: Supports Ansible's C(--diff) for pending edge branch updates.
    support: full
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.6.0
seealso:
  - module: graphiant.naas.graphiant_macsec_info
    description: Query MACsec secure/unsecure monitoring status per interface.
  - module: graphiant.naas.graphiant_interfaces
    description: Configure LAN/WAN interfaces before applying MACsec.
  - module: graphiant.naas.graphiant_lag_interfaces
    description: Configure LAG interfaces before applying MACsec on LAGs.
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
# Load vault_secrets.yml with M(ansible.builtin.include_vars) first (see macsec_management.yml).

- name: Apply MACsec from sample_macsec.yaml
  graphiant.naas.graphiant_macsec:
    operation: configure
    macsec_config_file: "sample_macsec.yaml"
    vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: macsec_result
  no_log: true

- name: Enable MACsec on a LAG interface (secrets from vault or module params)
  graphiant.naas.graphiant_macsec:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-1-sdktest"
    vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
    interfaces:
      LAG1:
        enabled: true
        encryptionEnforcementMode: MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT
        keyServerPriority: 200
        presharedKeys:
          - nickname: macsec-key-1
            startTime: "2029-12-11 11:12:13"
            ckn: "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956"
            cipherSuite: AES_256_CMAC
            useXpnForCipherSuite: true
        sakConfiguration:
          replayProtectionWindowSize: 64
          rekeyInterval: 3600
  no_log: true

- name: Disable MACsec on an interface
  graphiant.naas.graphiant_macsec:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-1-sdktest"
    interfaces:
      LAG1:
        enabled: false

- name: Rotate MACsec keys (add new key, remove old)
  graphiant.naas.graphiant_macsec:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-1-sdktest"
    interfaces:
      GigabitEthernet7/0/0:
        presharedKeys:
          - nickname: key1
            state: absent
          - nickname: key2
            startTime: "2029-12-11 23:12:13"
            ckn: "24"
            cipherSuite: AES_256_CMAC
    vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
  no_log: true

- name: Update SAK replay window only
  graphiant.naas.graphiant_macsec:
    operation: configure
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    device: "edge-1-sdktest"
    interfaces:
      LAG1:
        sakConfiguration:
          replayProtectionWindowSize: 128
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
macsec_config_file:
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


def _has_macsec_params(module_params: Dict[str, Any]) -> bool:
    interfaces = module_params.get("interfaces")
    return isinstance(interfaces, dict) and bool(interfaces)


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
    if params.get("interfaces") is not None:
        mp["interfaces"] = params["interfaces"]
    return mp


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        macsec_config_file=dict(type="str", required=False, default=None, aliases=["macsec_file"]),
        device=dict(type="str", required=False, default=None),
        interfaces=dict(type="dict", required=False, default=None),
        vault_devices_macsec_psk=dict(type="dict", required=False, default={}, no_log=True),
        operation=dict(type="str", required=False, default="configure", choices=["configure"]),
        state=dict(type="str", required=False, default="present", choices=["present"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation") or "configure"
    state = params.get("state", "present")
    cfg_file = params.get("macsec_config_file")
    device = (params.get("device") or "").strip()
    module_params = _module_params_from_ansible(params)

    if state != "present":
        module.fail_json(msg="Only state=present is supported.", operation=operation)
        return

    if not cfg_file and not device:
        module.fail_json(
            msg="Provide macsec_config_file and/or device (portal device name).",
            operation=operation,
        )
        return

    vault_psk = params.get("vault_devices_macsec_psk") or {}
    if not isinstance(vault_psk, dict):
        vault_psk = {}

    if not cfg_file and not _has_macsec_params(module_params):
        module.fail_json(
            msg="When macsec_config_file is omitted, interfaces is required for the target device.",
            operation=operation,
        )
        return

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.macsec.configure,
                cfg_file,
                module_params,
                vault_psk,
                success_msg="Successfully applied MACsec settings",
                no_change_msg="MACsec already matches desired state; no changes needed",
            )
            details = result.get("details") or {}
            if details.get("no_input"):
                module.exit_json(
                    changed=False,
                    msg="No macsec entries in YAML; nothing to do.",
                    operation=operation,
                    details=details,
                )
                return

            exit_payload = dict(
                changed=result["changed"],
                msg=result["result_msg"],
                operation=operation,
                configured_devices=result.get("configured_devices", []),
                skipped_devices=result.get("skipped_devices", []),
                details=details,
            )
            if cfg_file:
                exit_payload["macsec_config_file"] = cfg_file
            apply_module_diff(module, exit_payload, details)
            module.exit_json(**exit_payload)
            return

        module.fail_json(msg=f"Unsupported operation: {operation}", operation=operation)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
