#!/usr/bin/python
# -*- coding:utf-8 -*-

# Copyright(C) 2023 IEIT Inc. All Rights Reserved.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = '''
---
module: generate_ssl
version_added: "4.0.0"
author:
    - WangBaoshan (@ieisystem)
short_description: Generate SSL certificate
description:
   - Generate SSL certificate on ieisystem Server.
notes:
   - Does not support C(check_mode).
options:
    common_name:
        description:
            - Common name for which the certificate is to be generated.
            - Maximum length of 64 alpha-numeric characters.
            - Special characters '\', '#' and '$' are not allowed.
        required: true
        type: str
    organization:
        description:
            - Name of the organization for which certificate is to be generated.
            - Maximum length of 64 alpha-numeric characters.
            - Special characters '\', '#' and '$' are not allowed.
        required: true
        type: str
    organization_unit:
        description:
            - Section or Unit of the organization for which certificate is to be generated.
            - Maximum length of 64 alpha-numeric characters.
            - Special characters '\', '#' and '$' are not allowed.
        required: true
        type: str
    city_locality:
        description:
            - City or Locality.
            - Maximum length of 128 alpha-numeric characters.
            - Special characters '\', '#' and '$' are not allowed.
        required: true
        type: str
    state_province:
        description:
            - State or Province.
            - Maximum length of 128 alpha-numeric characters.
            - Special characters '\', '#' and '$' are not allowed.
        required: true
        type: str
    country:
        description:
            - Country code.
            - Only two characters are allowed.
            - Special characters are not allowed.
        required: true
        type: str
    email:
        description:
            - Email Address of the organization.
        required: true
        type: str
    valid_time:
        description:
            - Requested validity days for the certificate.
            - Value ranges from 1 to 3650 days.
        required: true
        type: int
extends_documentation_fragment:
    - ieisystem.inmanage.inmanage
'''

EXAMPLES = '''
- name: Generate SSL test
  hosts: inmanage
  connection: local
  gather_facts: false
  vars:
    inmanage:
      host: "{{ ansible_ssh_host }}"
      username: "{{ username }}"
      password: "{{ password }}"

  tasks:

  - name: "Generate SSL"
    ieisystem.inmanage.generate_ssl:
      common_name: "tests"
      organization: "test"
      organization_unit: "yanfa"
      city_locality: "jinan"
      state_province: "Shandong"
      country: "CN"
      email: "wbdddu@test.com"
      valid_time: 10
      provider: "{{ inmanage }}"

'''

RETURN = '''
message:
    description: Messages returned after module execution.
    returned: always
    type: str
state:
    description: Status after module execution.
    returned: always
    type: str
changed:
    description: Check to see if a change was made on the device.
    returned: always
    type: bool
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ieisystem.inmanage.plugins.module_utils.inmanage import (inmanage_argument_spec, get_connection)


class SSL(object):
    def __init__(self, argument_spec):
        self.spec = argument_spec
        self.module = None
        self.init_module()
        self.results = dict()

    def init_module(self):
        """Init module object"""

        self.module = AnsibleModule(
            argument_spec=self.spec, supports_check_mode=False)

    def run_command(self):
        self.module.params['subcommand'] = 'setssl'
        self.results = get_connection(self.module)
        if self.results['State'] == 'Success':
            self.results['changed'] = True

    def show_result(self):
        """Show result"""
        self.module.exit_json(**self.results)

    def work(self):
        """Worker"""
        self.run_command()
        self.show_result()


def main():
    argument_spec = dict(
        common_name=dict(type='str', required=True),
        organization=dict(type='str', required=True),
        organization_unit=dict(type='str', required=True),
        city_locality=dict(type='str', required=True),
        state_province=dict(type='str', required=True),
        country=dict(type='str', required=True),
        email=dict(type='str', required=True),
        valid_time=dict(type='int', required=True),
    )
    argument_spec.update(inmanage_argument_spec)
    ssl_obj = SSL(argument_spec)
    ssl_obj.work()


if __name__ == '__main__':
    main()
