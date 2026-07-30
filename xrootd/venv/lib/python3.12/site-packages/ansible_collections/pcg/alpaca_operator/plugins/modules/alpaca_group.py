#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: Contributors to the Ansible project
# Apache License, Version 2.0 (see LICENSE or https://www.apache.org/licenses/LICENSE-2.0)


from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: alpaca_group

short_description: Manage ALPACA Operator groups via REST API

version_added: '1.0.0'

extends_documentation_fragment:
    - pcg.alpaca_operator.api_connection

description: This module allows you to create, rename or delete ALPACA Operator groups using the REST API.

options:
    name:
        description: Name of the group.
        version_added: '1.0.0'
        required: true
        type: str
    new_name:
        description: >
            Optional new name for the group. If the group specified in O(name) exists,
            it will be renamed to this value. If the group does not exist, a new group will
            be created using this value.
        version_added: '1.0.0'
        required: false
        type: str
    state:
        description: Desired state of the group.
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
- name: Ensure group exists
  pcg.alpaca_operator.alpaca_group:
    name: testgroup01
    state: present
    api_connection:
      host: localhost
      port: 8443
      protocol: https
      username: secret
      password: secret
      tls_verify: false

- name: Ensure group is absent
  pcg.alpaca_operator.alpaca_group:
    name: testgroup01
    state: absent
    api_connection:
      host: localhost
      port: 8443
      protocol: https
      username: secret
      password: secret
      tls_verify: false

- name: Rename an existing group
  pcg.alpaca_operator.alpaca_group:
    name: testgroup01
    new_name: testgroup_renamed
    state: present
    api_connection:
      host: localhost
      port: 8443
      protocol: https
      username: secret
      password: secret
      tls_verify: false
'''

RETURN = r'''
changed:
    description: Indicates whether any change was made to the group
    version_added: '1.0.0'
    returned: always
    type: bool
    sample: true

msg:
    description: Human-readable message describing the outcome
    version_added: '1.0.0'
    returned: always
    type: str
    sample: Group created

id:
    description: Numeric ID of the group (if known or newly created)
    version_added: '1.0.0'
    returned: when state is present or absent and group exists
    type: int
    sample: 42

name:
    description: Name of the group (new or existing)
    version_added: '1.0.0'
    returned: always
    type: str
    sample: testgroup01
'''

from ansible_collections.pcg.alpaca_operator.plugins.module_utils._alpaca_api import get_token, get_api_connection_argument_spec, api_call
from ansible.module_utils.basic import AnsibleModule


def find_group(api_url, headers, name, verify):
    """Find group by name"""
    response = api_call("GET", "{0}/groups".format(api_url), headers=headers, verify=verify)
    for group in response.json():
        if group["name"] == name:
            return group
    return None


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),
            new_name=dict(type='str', required=False),
            state=dict(type='str', required=False, default='present', choices=['present', 'absent']),
            api_connection=get_api_connection_argument_spec()
        ),
        supports_check_mode=True,
    )

    name = module.params['name']
    new_name = module.params.get('new_name')
    state = module.params['state']
    api_host = module.params['api_connection']['host']
    api_port = module.params['api_connection']['port']
    api_protocol = module.params['api_connection']['protocol']
    api_username = module.params['api_connection']['username']
    api_password = module.params['api_connection']['password']
    api_tls_verify = module.params['api_connection']['tls_verify']
    api_url = "{0}://{1}:{2}/api".format(api_protocol, api_host, api_port)
    api_token = get_token(api_url, api_username, api_password, api_tls_verify)

    headers = {"Authorization": "Bearer {0}".format(api_token)}
    group = find_group(api_url, headers, name, api_tls_verify)

    if state == 'present':
        if group:
            # If renaming is requested and name differs, perform update
            if new_name and new_name != name:
                if module.check_mode:
                    module.exit_json(changed=True, msg="Group would be renamed", id=group["id"], name=new_name)

                if not find_group(api_url, headers, new_name, api_tls_verify):
                    response = api_call(
                        "PUT",
                        "{0}/groups/{1}".format(api_url, group["id"]),
                        headers=headers,
                        verify=api_tls_verify,
                        json={"name": new_name},
                        module=module,
                        fail_msg="Failed to rename group"
                    )

                    if response.status_code not in [200]:
                        module.fail_json(msg="Failed to rename group: {0}".format(response.text))

                    module.exit_json(changed=True, msg="Group renamed", id=group["id"], name=new_name)

            # No changes needed
            module.exit_json(changed=False, msg="Group already exists", id=group["id"], name=group["name"])

        # Create the group if it doesn't exist
        if new_name:
            name = new_name

        if not find_group(api_url, headers, name, api_tls_verify):
            if module.check_mode:
                module.exit_json(changed=True, msg="Group would be created", name=name)

            response = api_call(
                "POST",
                "{0}/groups".format(api_url),
                headers=headers,
                verify=api_tls_verify,
                json={"name": name},
                module=module,
                fail_msg="Failed to create group"
            )
            module.exit_json(changed=True, msg="Group created", id=response.json()["id"], name=name)

        module.exit_json(changed=False, msg="Group already exists", name=name)

    if state == 'absent':
        if not group:
            module.exit_json(changed=False, msg="Group does not exist", name=name)
        if module.check_mode:
            module.exit_json(changed=True, msg="Group would be deleted", id=group["id"], name=name)

        group_id = group["id"]
        response = api_call(
            "DELETE",
            "{0}/groups/{1}".format(api_url, group_id),
            headers=headers,
            verify=api_tls_verify,
            module=module,
            fail_msg="Failed to delete group"
        )

        if response.status_code not in [204]:
            module.fail_json(msg="Failed to delete group: {0}".format(response.text))
        module.exit_json(changed=True, msg="Group deleted", id=group["id"], name=name)


if __name__ == '__main__':
    main()
