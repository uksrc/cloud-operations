#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: Contributors to the Ansible project
# Apache License, Version 2.0 (see LICENSE or https://www.apache.org/licenses/LICENSE-2.0)


from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: alpaca_agent

short_description: Manage ALPACA Operator agents via REST API

version_added: '1.0.0'

extends_documentation_fragment:
    - pcg.alpaca_operator.api_connection

description: This module allows you to create, update or delete ALPACA Operator agents using the REST API.

options:
    name:
        description: Unique name (hostname) of the agent.
        version_added: '1.0.0'
        required: true
        type: str
    new_name:
        description: >
            Optional new name for the agent. If the agent specified in O(name) exists,
            it will be renamed to this value. If the agent does not exist, a new agent will
            be created using this value.
        version_added: '1.0.0'
        required: false
        type: str
    description:
        description: Unique description of the agent.
        version_added: '1.0.0'
        required: false
        type: str
    escalation:
        description: Escalation configuration.
        version_added: '1.0.0'
        required: false
        type: dict
        suboptions:
            failures_before_report:
                description: Number of failures before reporting.
                version_added: '2.0.0'
                required: false
                type: int
                default: 0
            mail_enabled:
                description: Whether mail notification is enabled.
                version_added: '2.0.0'
                required: false
                type: bool
                default: false
            mail_address:
                description: Mail address for notifications.
                version_added: '2.0.0'
                required: false
                type: str
                default: ""
            sms_enabled:
                description: Whether SMS notification is enabled.
                version_added: '2.0.0'
                required: false
                type: bool
                default: false
            sms_address:
                description: SMS address for notifications.
                version_added: '2.0.0'
                required: false
                type: str
                default: ""
    ip_address:
        description: IP address of the agent.
        version_added: '2.0.0'
        required: false
        type: str
    location:
        description: Location of the agent. Can be V(virtual), V(local1), V(local2), or V(remote).
        version_added: '1.0.0'
        required: false
        type: str
        choices: [virtual, local1, local2, remote]
        default: virtual
    script_group_id:
        description: Script Group ID.
        version_added: '2.0.0'
        required: false
        type: int
        default: -1
    state:
        description: Desired state of the agent.
        version_added: '1.0.0'
        required: false
        default: present
        choices: [present, absent]
        type: str

requirements:
    - ALPACA Operator >= 5.6.0

attributes:
    check_mode:
        description: Can run in check_mode and return changed status prediction without modifying target.
        support: full

author:
    - Jan-Karsten Hansmeyer (@pcg)
'''

EXAMPLES = r'''
- name: Ensure agent exists
  pcg.alpaca_operator.alpaca_agent:
    name: agent01
    ip_address: 192.168.1.100
    location: virtual
    description: Test agent
    escalation:
      failures_before_report: 3
      mail_enabled: true
      mail_address: my.mail@pcg.io
      sms_enabled: true
      sms_address: 0123456789
    script_group_id: 0
    state: present
    api_connection:
      host: localhost
      port: 8443
      protocol: https
      username: secret
      password: secret
      tls_verify: False

- name: Ensure agent is absent
  pcg.alpaca_operator.alpaca_agent:
    name: agent01
    state: absent
    api_connection:
      host: localhost
      port: 8443
      protocol: https
      username: secret
      password: secret
      tls_verify: False

- name: Rename an existing agent
  pcg.alpaca_operator.alpaca_agent:
    name: agent01
    new_name: agent_renamed
    state: present
    api_connection:
      host: localhost
      port: 8443
      protocol: https
      username: secret
      password: secret
      tls_verify: False
'''

RETURN = r'''
msg:
    description: Status message indicating the result of the operation
    returned: always
    type: str
    version_added: '1.0.0'
    sample: Agent created

changed:
    description: Indicates whether any change was made
    returned: always
    type: bool
    version_added: '1.0.0'
    sample: true

agent_config:
    description: Details of the created, updated, or deleted agent configuration
    returned: when state is present or absent
    type: dict
    version_added: '1.0.0'
    sample:
        id: 7
        hostname: "testagent"
        description: "Test agent"
        ip_address: "10.1.1.1"
        location: "virtual"
        script_group_id: 2
        escalation:
            failures_before_report: 3
            mail_enabled: true
            mail_address: "monitoring@pcg.io"
            sms_enabled: false
            sms_address: ""

changes:
    description: Dictionary showing differences between the current and desired configuration
    returned: when state is present and a change occurred
    type: dict
    version_added: '1.0.0'
    sample:
        ip_address:
            current: "10.1.1.1"
            desired: "10.1.1.2"
        escalation:
            mail_enabled:
                current: false
                desired: true
'''

from ansible_collections.pcg.alpaca_operator.plugins.module_utils._alpaca_api import api_call, get_token, lookup_resource, get_api_connection_argument_spec
from ansible.module_utils.basic import AnsibleModule


def build_payload(desired_agent_config, current_agent_config):
    """
    Constructs a configuration payload by prioritizing values from the desired configuration
    dictionary. If a value is not provided in the desired configuration, the function falls
    back to using the corresponding value from the existing configuration (if available).

    Parameters:
        desired_agent_config (dict): A dictionary containing the desired configuration values.
        current_agent_config (dict): A dictionary with existing configuration values.

    Returns:
        dict: A combined configuration payload dictionary.
    """

    payload = {
        "description":              desired_agent_config.get('description', None)                                           if desired_agent_config.get('description', None)                                            is not None else current_agent_config.get('description', ''),
        "escalation": {
            "failuresBeforeReport": (desired_agent_config.get('escalation') or {}).get('failures_before_report', None)     if (desired_agent_config.get('escalation') or {}).get('failures_before_report', None)      is not None else current_agent_config.get('escalation', {}).get('failuresBeforeReport', 0),
            "mailAddress":          (desired_agent_config.get('escalation') or {}).get('mail_address', None)                if (desired_agent_config.get('escalation') or {}).get('mail_address', None)                 is not None else current_agent_config.get('escalation', {}).get('mailAddress', ''),
            "mailEnabled":          (desired_agent_config.get('escalation') or {}).get('mail_enabled', None)                if (desired_agent_config.get('escalation') or {}).get('mail_enabled', None)                 is not None else current_agent_config.get('escalation', {}).get('mailEnabled', False),
            "smsAddress":           (desired_agent_config.get('escalation') or {}).get('sms_address', None)                 if (desired_agent_config.get('escalation') or {}).get('sms_address', None)                  is not None else current_agent_config.get('escalation', {}).get('smsAddress', ''),
            "smsEnabled":           (desired_agent_config.get('escalation') or {}).get('sms_enabled', None)                 if (desired_agent_config.get('escalation') or {}).get('sms_enabled', None)                  is not None else current_agent_config.get('escalation', {}).get('smsEnabled', False),
        },
        "hostname":                 desired_agent_config.get('new_name', None) or desired_agent_config.get('name', None)    if desired_agent_config.get('new_name', None) or desired_agent_config.get('name', None)     is not None else current_agent_config.get('hostname', ''),
        "ipAddress":                desired_agent_config.get('ip_address', None)                                            if desired_agent_config.get('ip_address', None)                                             is not None else current_agent_config.get('ipAddress', ''),
        "location":                 desired_agent_config.get('location', None)                                              if desired_agent_config.get('location', None)                                               is not None else current_agent_config.get('location', 'virtual'),
        "scriptGroupId":            desired_agent_config.get('script_group_id', None)                                       if desired_agent_config.get('script_group_id', None)                                        is not None else current_agent_config.get('scriptGroupId', -1),
    }

    return payload


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),       # = hostname
            new_name=dict(type='str', required=False),  # = hostname
            description=dict(type='str', required=False),
            escalation=dict(type='dict', required=False),
            ip_address=dict(type='str', required=False),
            location=dict(type='str', required=False, default='virtual', choices=['virtual', 'local1', 'local2', 'remote']),
            script_group_id=dict(type='int', required=False, default=-1),
            state=dict(type='str', required=False, default='present', choices=['present', 'absent']),
            api_connection=get_api_connection_argument_spec()
        ),
        supports_check_mode=True,
    )

    api_url = "{0}://{1}:{2}/api".format(module.params['api_connection']['protocol'], module.params['api_connection']['host'], module.params['api_connection']['port'])
    token = get_token(api_url, module.params['api_connection']['username'], module.params['api_connection']['password'], module.params['api_connection']['tls_verify'])
    headers = {"Authorization": "Bearer {0}".format(token)}
    current_agent = lookup_resource(api_url, headers, "agents", "hostname", module.params['name'], module.params['api_connection']['tls_verify']) or lookup_resource(api_url, headers, "agents", "hostname", module.params['new_name'], module.params['api_connection']['tls_verify'])
    current_agent_config = api_call(method="GET", url="{0}/agents/{1}".format(api_url, current_agent.get('id', None)), headers=headers, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to get current agent configuration").json() if current_agent else {}
    agent_payload = build_payload(module.params, current_agent_config)
    diff = {}

    if module.params['state'] == 'present':
        if current_agent:
            # Compare current agent configuration with the desired agent configuration if it already exists
            for key in agent_payload:
                if key not in ['escalation']:
                    if agent_payload.get(key, None) != current_agent_config.get(key, None):
                        diff[key] = {
                            'current': current_agent_config.get(key, None),
                            'desired': agent_payload.get(key, None)
                        }
                if key in ['escalation']:
                    for sub_key in agent_payload.get(key, {}):
                        if agent_payload.get(key, {}).get(sub_key, None) != current_agent_config.get(key, {}).get(sub_key, None):
                            if key not in diff:
                                diff[key] = {}
                            diff[key][sub_key] = {
                                'current': current_agent_config.get(key, {}).get(sub_key, None),
                                'desired': agent_payload.get(key, {}).get(sub_key, None)
                            }

            if diff:
                if module.check_mode:
                    module.exit_json(changed=True, msg="Agent would be updated", changes=diff)

                # Update agent
                current_agent_config = api_call("PUT", "{0}/agents/{1}".format(api_url, current_agent['id']), headers=headers, json=agent_payload, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to update agent").json()
                module.exit_json(changed=True, msg="Agent updated", agent_config=current_agent_config, changes=diff)

        elif not current_agent:
            if module.check_mode:
                module.exit_json(changed=True, msg="Agent would be created", agent_config=agent_payload)

            # Create the agent if it doesn't exist
            current_agent_config = api_call("POST", "{0}/agents".format(api_url), headers=headers, json=agent_payload, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to create agent").json()
            module.exit_json(changed=True, msg="Agent created", agent_config=current_agent_config)

        module.exit_json(changed=False, msg="Agent already exists with the desired configuration", agent_config=current_agent_config)

    elif module.params['state'] == 'absent':
        if not current_agent:
            module.exit_json(changed=False, msg="Agent already absent")

        if module.check_mode:
            module.exit_json(changed=True, msg="Agent would be unassigned from all systems and deleted", agent_config=current_agent_config)

        # Get all systems
        systems = api_call(method="GET", url="{0}/systems".format(api_url), headers=headers, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to retrieve systems").json()

        # Iterate through all systems and check for agent assignments and commands
        for system in systems:
            # List agents
            # module.warn("Retrieve agents for system {0}...".format(system['id']))
            agents = api_call(method="GET", url="{0}/systems/{1}/agents".format(api_url, system['id']), headers=headers, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to retrieve agents").json()

            # Check if the agent ID we are looking for is assigned to this system
            if any(agent['id'] == current_agent['id'] for agent in agents):
                # Unassign agent from system
                # module.warn("Unassign agent {0} from system {1}".format(current_agent['id'], system['id']))
                api_call(method="DELETE", url="{0}/systems/{1}/agents/{2}".format(api_url, system['id'], current_agent['id']), headers=headers, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to unassign agent")

        # Delete agent with retries
        api_call("DELETE", "{0}/agents/{1}".format(api_url, current_agent['id']), headers=headers, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to delete agent")
        module.exit_json(changed=True, msg="Agent deleted", agent_config=current_agent_config)

    module.exit_json(changed=True, msg="Agent state processed")


if __name__ == '__main__':
    main()
