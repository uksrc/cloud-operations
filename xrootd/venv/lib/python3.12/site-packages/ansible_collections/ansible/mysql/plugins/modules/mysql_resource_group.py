#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible community
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_resource_group

short_description: Add, update, or remove MySQL resource groups

description:
  - Add, update, or remove MySQL resource groups.
  - Resource groups are supported by MySQL 8.0 or later.

version_added: '5.1.0'

options:
  name:
    description:
      - Name of the resource group to manage.
    type: str
    required: true
  state:
    description:
      - If C(present), creates the resource group when it does not exist.
      - If C(present), updates mutable attributes when the resource group already exists.
      - If C(absent), removes the resource group.
    type: str
    choices: [absent, present]
    default: present
  resource_group_type:
    description:
      - Resource group type.
      - Required when creating a new resource group.
      - The value is immutable after creation.
    type: str
    choices: [SYSTEM, USER]
  vcpu_ids:
    description:
      - CPU affinity in native MySQL syntax.
      - Examples include C(0-3) and C(0-3,8,10-12).
      - When omitted for an existing resource group, the current value is left unchanged.
    type: str
  thread_priority:
    description:
      - Thread priority to set for the resource group.
      - Must be between C(-20) and C(0) for C(SYSTEM) resource groups.
      - Must be between C(0) and C(19) for C(USER) resource groups.
      - When omitted for an existing resource group, the current value is left unchanged.
    type: int
  enabled:
    description:
      - Whether the resource group should be enabled.
      - When omitted for an existing resource group, the current value is left unchanged.
    type: bool
  force:
    description:
      - If C(true), use C(FORCE) when dropping a resource group.
      - This only applies when O(state=absent).
    type: bool
    default: false

notes:
  - This module supports MySQL 8.0 or later only.
  - Resource groups are not available on MariaDB.
  - MySQL documents resource groups as unavailable when the thread pool plugin is installed.
  - Thread-priority behavior can depend on server platform and operating-system capabilities.

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
  - module: ansible.mysql.mysql_resource_group_info
  - name: MySQL CREATE RESOURCE GROUP reference
    description: Complete reference of the CREATE RESOURCE GROUP command documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/create-resource-group.html
  - name: MySQL ALTER RESOURCE GROUP reference
    description: Complete reference of the ALTER RESOURCE GROUP command documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/alter-resource-group.html
  - name: MySQL DROP RESOURCE GROUP reference
    description: Complete reference of the DROP RESOURCE GROUP command documentation.
    link: https://dev.mysql.com/doc/refman/8.4/en/drop-resource-group.html

author:
  - Ron Gershburg (@ronger4)


extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
# If you encounter the "Please explicitly state intended protocol" error,
# use the login_unix_socket argument
- name: Create a reporting resource group
  ansible.mysql.mysql_resource_group:
    name: reporting
    resource_group_type: USER
    vcpu_ids: 4-7
    thread_priority: 5
    enabled: true
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Disable a resource group
  ansible.mysql.mysql_resource_group:
    name: reporting
    state: present
    enabled: false

- name: Drop a resource group and reassign running threads
  ansible.mysql.mysql_resource_group:
    name: reporting
    state: absent
    force: true
'''

RETURN = r'''
queries:
  description: List of executed queries.
  returned: when changed
  type: list
  sample: ["CREATE RESOURCE GROUP `reporting` TYPE = USER VCPU = 4-7 THREAD_PRIORITY = 5 ENABLE"]
resource_group:
  description: Normalized representation of the resource group after module execution.
  returned: when O(state=present)
  type: dict
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
from ansible_collections.ansible.mysql.plugins.module_utils.database import mysql_quote_identifier
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)
from ansible_collections.ansible.mysql.plugins.module_utils.resource_group import (
    ensure_resource_groups_supported,
    normalize_resource_group_enabled as normalize_enabled,
    normalize_resource_group_row,
    normalize_vcpu_ids,
    validate_resource_group_type,
    validate_thread_priority,
)

DEFAULT_RESOURCE_GROUPS = ('SYS_default', 'USR_default')
RESOURCE_GROUP_QUERY = (
    'SELECT RESOURCE_GROUP_NAME, RESOURCE_GROUP_TYPE, RESOURCE_GROUP_ENABLED, VCPU_IDS, THREAD_PRIORITY '
    'FROM INFORMATION_SCHEMA.RESOURCE_GROUPS WHERE RESOURCE_GROUP_NAME = %s'
)


def normalize_resource_group_inputs(resource_group_type=None, vcpu_ids=None):
    if resource_group_type is not None:
        resource_group_type = validate_resource_group_type(resource_group_type)
    if vcpu_ids is not None:
        vcpu_ids = normalize_vcpu_ids(vcpu_ids)
    return resource_group_type, vcpu_ids


def build_create_query(name, resource_group_type, vcpu_ids=None, thread_priority=None, enabled=None):
    query = [
        'CREATE RESOURCE GROUP %s' % mysql_quote_identifier(name, 'role'),
        'TYPE = %s' % resource_group_type,
    ]

    if vcpu_ids is not None:
        query.append('VCPU = %s' % vcpu_ids)

    if thread_priority is not None:
        query.append('THREAD_PRIORITY = %s' % validate_thread_priority(resource_group_type, thread_priority))

    if enabled is True:
        query.append('ENABLE')
    elif enabled is False:
        query.append('DISABLE')

    return ' '.join(query)


def build_alter_query(name, current, resource_group_type=None, vcpu_ids=None, thread_priority=None, enabled=None):
    if resource_group_type is not None:
        if current['resource_group_type'] != resource_group_type:
            raise ValueError('resource_group_type is immutable after creation')

    changes = []

    if vcpu_ids is not None:
        if current['vcpu_ids'] != vcpu_ids:
            changes.append('VCPU = %s' % vcpu_ids)

    if thread_priority is not None:
        normalized_priority = validate_thread_priority(current['resource_group_type'], thread_priority)
        if current['thread_priority'] != normalized_priority:
            changes.append('THREAD_PRIORITY = %s' % normalized_priority)

    if enabled is not None:
        normalized_enabled = normalize_enabled(enabled)
        if current['enabled'] != normalized_enabled:
            changes.append('ENABLE' if normalized_enabled else 'DISABLE')

    if not changes:
        return None

    return 'ALTER RESOURCE GROUP %s %s' % (mysql_quote_identifier(name, 'role'), ' '.join(changes))


def build_drop_query(name, force=False):
    query = 'DROP RESOURCE GROUP %s' % mysql_quote_identifier(name, 'role')
    if force:
        query += ' FORCE'
    return query


def get_resource_group(cursor, name):
    cursor.execute(RESOURCE_GROUP_QUERY, (name,))
    row = cursor.fetchone()
    if not row:
        return None
    return normalize_resource_group_row(row)


def execute_query(cursor, query):
    cursor.execute(query)


def fail_if_default_resource_group(module, name):
    if name in DEFAULT_RESOURCE_GROUPS:
        module.fail_json(msg='Default resource groups cannot be altered or dropped: %s' % name)


def fail_if_effective_thread_priority_differs(module, requested_thread_priority, current, queries):
    if requested_thread_priority is None:
        return

    if current['thread_priority'] != requested_thread_priority:
        module.fail_json(
            msg=('thread_priority %s could not be applied; server reported %s. '
                 'The server may ignore thread priorities on this platform.'
                 % (requested_thread_priority, current['thread_priority'])),
            changed=True,
            queries=queries,
            resource_group=current,
        )


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        name=dict(type='str', required=True),
        state=dict(type='str', choices=['absent', 'present'], default='present'),
        resource_group_type=dict(type='str', choices=['SYSTEM', 'USER']),
        vcpu_ids=dict(type='str'),
        thread_priority=dict(type='int'),
        enabled=dict(type='bool'),
        force=dict(type='bool', default=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    name = module.params['name']
    state = module.params['state']
    resource_group_type = module.params['resource_group_type']
    vcpu_ids = module.params['vcpu_ids']
    thread_priority = module.params['thread_priority']
    enabled = module.params['enabled']
    force = module.params['force']
    login_user = module.params['login_user']
    login_password = module.params['login_password']
    config_file = module.params['config_file']
    ssl_cert = module.params['client_cert']
    ssl_key = module.params['client_key']
    ssl_ca = module.params['ca_cert']
    connect_timeout = module.params['connect_timeout']
    check_hostname = module.params['check_hostname']

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
            autocommit=True,
        )
    except Exception as e:
        module.fail_json(msg='unable to connect to database: %s' % to_native(e))

    ensure_resource_groups_supported(module, cursor)

    current = get_resource_group(cursor, name)
    queries = []

    try:
        resource_group_type, vcpu_ids = normalize_resource_group_inputs(resource_group_type, vcpu_ids)
    except ValueError as e:
        module.fail_json(msg=to_native(e))

    if state == 'absent':
        if current is None:
            module.exit_json(changed=False)

        fail_if_default_resource_group(module, name)
        query = build_drop_query(name, force)
        queries.append(query)

        if module.check_mode:
            module.exit_json(changed=True, queries=queries)

        try:
            execute_query(cursor, query)
        except Exception as e:
            module.fail_json(msg=to_native(e))

        module.exit_json(changed=True, queries=queries)

    if current is None:
        if resource_group_type is None:
            module.fail_json(msg='resource_group_type is required when creating a resource group')

        try:
            if thread_priority is not None:
                validate_thread_priority(resource_group_type, thread_priority)
        except ValueError as e:
            module.fail_json(msg=to_native(e))

        query = build_create_query(name, resource_group_type, vcpu_ids, thread_priority, enabled)
        queries.append(query)

        if module.check_mode:
            module.exit_json(
                changed=True,
                queries=queries,
                resource_group={
                    'name': name,
                    'resource_group_type': resource_group_type,
                    'enabled': True if enabled is None else enabled,
                    'vcpu_ids': vcpu_ids,
                    'thread_priority': 0 if thread_priority is None else thread_priority,
                },
            )

        try:
            execute_query(cursor, query)
        except Exception as e:
            module.fail_json(msg=to_native(e))

        current = get_resource_group(cursor, name)
        fail_if_effective_thread_priority_differs(module, thread_priority, current, queries)
        module.exit_json(changed=True, queries=queries, resource_group=current)

    try:
        if thread_priority is not None:
            validate_thread_priority(current['resource_group_type'], thread_priority)
        query = build_alter_query(name, current, resource_group_type, vcpu_ids, thread_priority, enabled)
    except ValueError as e:
        module.fail_json(msg=to_native(e))

    if query is None:
        module.exit_json(changed=False, resource_group=current)

    fail_if_default_resource_group(module, name)
    queries.append(query)

    if module.check_mode:
        module.exit_json(changed=True, queries=queries, resource_group=current)

    try:
        execute_query(cursor, query)
    except Exception as e:
        module.fail_json(msg=to_native(e))

    current = get_resource_group(cursor, name)
    fail_if_effective_thread_priority_differs(module, thread_priority, current, queries)
    module.exit_json(changed=True, queries=queries, resource_group=current)


if __name__ == '__main__':
    main()
