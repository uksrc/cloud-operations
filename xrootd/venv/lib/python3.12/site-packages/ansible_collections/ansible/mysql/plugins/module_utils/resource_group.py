from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.module_utils.common.text.converters import to_native

from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    get_server_implementation,
    get_server_version,
)


def get_server_version_tuple(cursor):
    version = get_server_version(cursor).split('-', 1)[0]
    version_tuple = []

    for part in version.split('.'):
        digits = ''.join(char for char in part if char.isdigit())
        if not digits:
            break
        version_tuple.append(int(digits))

    while len(version_tuple) < 3:
        version_tuple.append(0)

    return tuple(version_tuple[:3])


def ensure_resource_groups_supported(module, cursor):
    if get_server_implementation(cursor) != 'mysql':
        module.fail_json(msg='Resource groups are supported only by MySQL 8.0 or later.')

    if get_server_version_tuple(cursor) < (8, 0, 0):
        module.fail_json(msg='Resource groups are supported only by MySQL 8.0 or later.')

    try:
        cursor.execute("SELECT RESOURCE_GROUP_NAME FROM INFORMATION_SCHEMA.RESOURCE_GROUPS LIMIT 1")
        cursor.fetchall()
    except Exception as e:
        module.fail_json(msg='Resource groups are not supported by the server: %s' % to_native(e))


def normalize_vcpu_ids(vcpu_ids):
    if vcpu_ids is None:
        return None
    if isinstance(vcpu_ids, bytes):
        vcpu_ids = vcpu_ids.decode('utf-8')

    cpus = set()

    for raw_item in vcpu_ids.split(','):
        item = raw_item.strip()
        if not item:
            raise ValueError('vcpu_ids contains an empty element')

        if '-' in item:
            bounds = item.split('-', 1)
            if len(bounds) != 2 or not bounds[0] or not bounds[1]:
                raise ValueError('vcpu_ids contains an invalid range: %s' % item)
            start = int(bounds[0])
            end = int(bounds[1])
            if start > end:
                raise ValueError('vcpu_ids contains a descending range: %s' % item)
            cpus.update(range(start, end + 1))
        else:
            cpus.add(int(item))

    normalized = []
    sorted_cpus = sorted(cpus)
    range_start = None
    range_end = None

    for cpu in sorted_cpus:
        if range_start is None:
            range_start = cpu
            range_end = cpu
            continue

        if cpu == range_end + 1:
            range_end = cpu
            continue

        normalized.append(_format_cpu_range(range_start, range_end))
        range_start = cpu
        range_end = cpu

    if range_start is not None:
        normalized.append(_format_cpu_range(range_start, range_end))

    return ','.join(normalized)


def _format_cpu_range(start, end):
    if start == end:
        return str(start)
    return '%s-%s' % (start, end)


def normalize_resource_group_enabled(value):
    if isinstance(value, bool):
        return value
    return str(value).upper() in ('YES', '1', 'ON', 'TRUE', 'ENABLE', 'ENABLED')


def normalize_resource_group_row(row):
    return {
        'name': row['RESOURCE_GROUP_NAME'],
        'resource_group_type': row['RESOURCE_GROUP_TYPE'],
        'enabled': normalize_resource_group_enabled(row['RESOURCE_GROUP_ENABLED']),
        'vcpu_ids': normalize_vcpu_ids(row['VCPU_IDS']),
        'thread_priority': int(row['THREAD_PRIORITY']),
    }


def validate_resource_group_type(resource_group_type):
    normalized_type = resource_group_type.upper()
    if normalized_type not in ('SYSTEM', 'USER'):
        raise ValueError('resource_group_type must be SYSTEM or USER')
    return normalized_type


def validate_thread_priority(resource_group_type, thread_priority):
    if thread_priority < -20 or thread_priority > 19:
        raise ValueError('thread_priority must be between -20 and 19')

    if resource_group_type == 'SYSTEM' and thread_priority > 0:
        raise ValueError('thread_priority must be between -20 and 0 for SYSTEM resource groups')

    if resource_group_type == 'USER' and thread_priority < 0:
        raise ValueError('thread_priority must be between 0 and 19 for USER resource groups')

    return thread_priority
