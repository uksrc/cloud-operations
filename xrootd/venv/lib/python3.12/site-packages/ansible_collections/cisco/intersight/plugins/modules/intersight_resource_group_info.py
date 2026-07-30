#!/usr/bin/python
# -*- coding: utf-8 -*-

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = r'''
---
module: intersight_resource_group_info
short_description: Gather information about Resource Groups in Cisco Intersight
description:
  - Gather information about Resource Groups in L(Cisco Intersight,https://intersight.com).
  - Information can be filtered by O(name).
  - If no filters are passed, all Resource Groups will be returned.
  - Each Resource Group is enriched with C(domains) and C(sub_targets) fields
    parsed from the raw API selectors for easier consumption.
  - Resource Groups are account-level resources and are not scoped to an organization.
extends_documentation_fragment: intersight
options:
  name:
    description:
      - The name of the Resource Group to gather information from.
    type: str
author:
  - Ron Gershburg (@rgershbu)
'''

EXAMPLES = r'''
- name: Fetch a specific Resource Group by name
  cisco.intersight.intersight_resource_group_info:
    api_private_key: "{{ api_private_key }}"
    api_key_id: "{{ api_key_id }}"
    name: "ucs-domains-group"

- name: Fetch all Resource Groups
  cisco.intersight.intersight_resource_group_info:
    api_private_key: "{{ api_private_key }}"
    api_key_id: "{{ api_key_id }}"
'''

RETURN = r'''
api_response:
  description: The API response output returned by the specified resource, enriched with domains and sub_targets.
  returned: always
  type: list
  elements: dict
  sample:
    - Name: "ucs-domains-group"
      ObjectType: "resource.Group"
      Moid: "507f1f77bcf86cd799439099"
      domains:
        - "ucs-domain-1"
        - "ucs-domain-2"
      sub_targets:
        - serial: "FCH26387BD1"
          type: "Blade"
        - serial: "WZP26030TAV"
          type: "RackUnit"
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.cisco.intersight.plugins.module_utils.intersight import IntersightModule, intersight_argument_spec


def parse_moids_from_selector(selector_str):
    """Extract Moid values from a DeviceRegistrations selector string."""
    match = re.search(r"Moid in \(([^)]+)\)", selector_str)
    if match:
        return [m.strip("' ") for m in match.group(1).split(',')]
    return []


def parse_serials_from_selector(selector_str):
    """Extract Serial values from a Blades or RackUnits selector string."""
    match = re.search(r"Serial in \(([^)]+)\)", selector_str)
    if match:
        return [s.strip("' ") for s in match.group(1).split(',')]
    return []


def resolve_moids_to_target_names(intersight, moids):
    """Resolve DeviceRegistration Moids to their Target names."""
    target_names = []
    for moid in moids:
        intersight.get_resource(
            resource_path='/asset/Targets',
            query_params={
                '$filter': f"RegisteredDevice.Moid eq '{moid}'",
                '$select': 'Name',
            },
        )
        name = intersight.result['api_response'].get('Name')
        target_names.append(name if name else moid)
    return target_names


def enrich_resource_groups(intersight, groups):
    """Add domains and sub_targets fields to each resource group."""
    for group in groups:
        domains = []
        sub_targets = []

        for selector_entry in group.get('Selectors', []):
            selector_str = selector_entry.get('Selector', '')

            if '/asset/DeviceRegistrations' in selector_str:
                moids = parse_moids_from_selector(selector_str)
                names = resolve_moids_to_target_names(intersight, moids)
                domains.extend(names)

            elif '/compute/Blades' in selector_str:
                serials = parse_serials_from_selector(selector_str)
                sub_targets.extend({'serial': s, 'type': 'Blade'} for s in serials)

            elif '/compute/RackUnits' in selector_str:
                serials = parse_serials_from_selector(selector_str)
                sub_targets.extend({'serial': s, 'type': 'RackUnit'} for s in serials)

        group['domains'] = domains
        group['sub_targets'] = sub_targets

    return groups


def main():
    argument_spec = intersight_argument_spec.copy()
    argument_spec.update(
        name=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
    )

    intersight = IntersightModule(module)
    intersight.result['api_response'] = {}
    intersight.result['trace_id'] = ''

    resource_path = '/resource/Groups'

    query_params = intersight.set_query_params()

    intersight.get_resource(
        resource_path=resource_path,
        query_params=query_params,
        return_list=True,
    )

    groups = intersight.result['api_response']
    if not isinstance(groups, list):
        groups = [groups] if groups else []

    enriched = enrich_resource_groups(intersight, groups)

    intersight.result['api_response'] = enriched
    module.exit_json(**intersight.result)


if __name__ == '__main__':
    main()
