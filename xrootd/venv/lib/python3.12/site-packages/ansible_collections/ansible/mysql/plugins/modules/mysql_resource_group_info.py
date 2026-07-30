#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible community
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_resource_group_info

short_description: Gather information about MySQL resource groups

description:
  - Gather information about MySQL resource groups.
  - Resource groups are supported by MySQL 8.0 or later.

version_added: '5.1.0'

options:
  name:
    description:
      - Limit the collected information to a single resource group name.
    type: str

notes:
  - This module supports MySQL 8.0 or later only.
  - Resource groups are not available on MariaDB.

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
  - module: ansible.mysql.mysql_resource_group
  - name: INFORMATION_SCHEMA RESOURCE_GROUPS reference
    description: Complete reference of the INFORMATION_SCHEMA RESOURCE_GROUPS table documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/information-schema-resource-groups-table.html

author:
  - Ron Gershburg (@ronger4)

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
# If you encounter the "Please explicitly state intended protocol" error,
# use the login_unix_socket argument
- name: Gather all resource groups
  ansible.mysql.mysql_resource_group_info:
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Gather a single resource group
  ansible.mysql.mysql_resource_group_info:
    name: reporting
'''

RETURN = r'''
resource_groups:
  description: List of normalized resource groups.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Resource group name.
      type: str
      sample: reporting
    resource_group_type:
      description: Resource group type.
      type: str
      sample: USER
    enabled:
      description: Whether the resource group is enabled.
      type: bool
      sample: true
    vcpu_ids:
      description: Normalized CPU affinity.
      type: str
      sample: 4-7
    thread_priority:
      description: Resource-group thread priority.
      type: int
      sample: 5
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)
from ansible_collections.ansible.mysql.plugins.module_utils.resource_group import (
    ensure_resource_groups_supported,
    normalize_resource_group_row,
)


def get_resource_groups_info(cursor, name=None):
    query = (
        'SELECT RESOURCE_GROUP_NAME, RESOURCE_GROUP_TYPE, RESOURCE_GROUP_ENABLED, VCPU_IDS, THREAD_PRIORITY '
        'FROM INFORMATION_SCHEMA.RESOURCE_GROUPS'
    )
    params = None

    if name:
        query += ' WHERE RESOURCE_GROUP_NAME = %s'
        params = (name,)

    query += ' ORDER BY RESOURCE_GROUP_NAME'

    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    return {
        'resource_groups': [normalize_resource_group_row(row) for row in cursor.fetchall()]
    }


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    login_user = module.params['login_user']
    login_password = module.params['login_password']
    config_file = module.params['config_file']
    ssl_cert = module.params['client_cert']
    ssl_key = module.params['client_key']
    ssl_ca = module.params['ca_cert']
    connect_timeout = module.params['connect_timeout']
    check_hostname = module.params['check_hostname']
    name = module.params['name']

    try:
        cursor, db_conn = mysql_connect(
            module,
            login_user,
            login_password,
            config_file,
            ssl_cert,
            ssl_key,
            ssl_ca,
            connect_timeout=connect_timeout,
            check_hostname=check_hostname,
            cursor_class='DictCursor',
        )
    except Exception as e:
        module.fail_json(msg='unable to connect to database: %s' % to_native(e))

    ensure_resource_groups_supported(module, cursor)
    module.exit_json(changed=False, **get_resource_groups_info(cursor, name))


if __name__ == '__main__':
    main()
