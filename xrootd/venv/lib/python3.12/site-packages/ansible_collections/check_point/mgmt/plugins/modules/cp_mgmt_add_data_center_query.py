#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Ansible module to manage CheckPoint Firewall (c) 2019
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = """
---
module: cp_mgmt_add_data_center_query
short_description: Adds data-center-query objects on Checkpoint over Web Services API
description:
  - Adds data-center-query objects on Checkpoint devices.
  - All operations are performed over Web Services API.
  - Available from R81 management version.
version_added: "6.9.0"
author: "Dor Berenstein (@chkp-dorbe)"
options:
  name:
    description:
      - Object name.
    type: str
    required: True
  query_rules:
    description:
      - Data Center Query Rules.<br>There is an 'AND' operation between multiple Query Rules.
    type: list
    elements: dict
    suboptions:
      key_type:
        description:
          - The type of the "key" parameter.<br>Use "predefined" for these keys, type-in-data-center, name-in-data-center, and ip-address.<br>Use
            "tag" to query the Data Center tag's property.
        type: str
        choices: ['predefined', 'tag']
      key:
        description:
          - Defines in which Data Center property to query.<br>For key-type "predefined", use these keys, type-in-data-center,
            name-in-data-center, and ip-address.<br>For key-type "tag", use the Data Center tag key to query.<br>Keys are case-insensitive.
        type: str
      values:
        description:
          - The value(s) of the Data Center property to match the Query Rule.<br>Values are case-insensitive.<br>There is an 'OR' operation
            between multiple values.<br>For key-type "predefined" and key 'ip-address', the values must be an IPv4 or IPv6 address.<br>For key-type "tag", the
            values must be the Data Center tag values.
        type: list
        elements: str
  data_centers:
    description:
      - Collection of Data Center servers identified by the name or UID. use "All" to select all data centers.
    type: list
    elements: str
  color:
    description:
      - Color of the object. Should be one of existing colors.
    type: str
    choices: ['aquamarine', 'black', 'blue', 'crete blue', 'burlywood', 'cyan', 'dark green', 'khaki', 'orchid', 'dark orange', 'dark sea green',
             'pink', 'turquoise', 'dark blue', 'firebrick', 'brown', 'forest green', 'gold', 'dark gold', 'gray', 'dark gray', 'light green', 'lemon chiffon',
             'coral', 'sea green', 'sky blue', 'magenta', 'purple', 'slate blue', 'violet red', 'navy blue', 'olive', 'orange', 'red', 'sienna', 'yellow']
  comments:
    description:
      - Comments string.
    type: str
  details_level:
    description:
      - The level of detail for some of the fields in the response can vary from showing only the UID value of the object to a fully detailed
        representation of the object.
    type: str
    choices: ['uid', 'standard', 'full']
  tags:
    description:
      - Collection of tag identifiers.
    type: list
    elements: str
  ignore_warnings:
    description:
      - Apply changes ignoring warnings.
    type: bool
  ignore_errors:
    description:
      - Apply changes ignoring errors. You won't be able to publish such a changes. If ignore-warnings flag was omitted - warnings will also be ignored.
    type: bool
extends_documentation_fragment: check_point.mgmt.checkpoint_commands
"""

EXAMPLES = """
- name: add-data-center-query
  cp_mgmt_add_data_center_query:
    name: data-center-query1
"""

RETURN = """
cp_mgmt_add_data_center_query:
  description: The checkpoint add-data-center-query output.
  returned: always.
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.check_point.mgmt.plugins.module_utils.checkpoint import (
    checkpoint_argument_spec_for_commands,
    api_command,
)


def main():
    argument_spec = dict(
        name=dict(type="str", required=True),
        query_rules=dict(
            type="list",
            elements="dict",
            options=dict(
                key_type=dict(type="str", choices=["predefined", "tag"]),
                key=dict(type="str", no_log=False),
                values=dict(type="list", elements="str"),
            ),
        ),
        data_centers=dict(type="list", elements="str"),
        color=dict(
            type="str",
            choices=[
                "aquamarine",
                "black",
                "blue",
                "crete blue",
                "burlywood",
                "cyan",
                "dark green",
                "khaki",
                "orchid",
                "dark orange",
                "dark sea green",
                "pink",
                "turquoise",
                "dark blue",
                "firebrick",
                "brown",
                "forest green",
                "gold",
                "dark gold",
                "gray",
                "dark gray",
                "light green",
                "lemon chiffon",
                "coral",
                "sea green",
                "sky blue",
                "magenta",
                "purple",
                "slate blue",
                "violet red",
                "navy blue",
                "olive",
                "orange",
                "red",
                "sienna",
                "yellow",
            ],
        ),
        comments=dict(type="str"),
        details_level=dict(type="str", choices=["uid", "standard", "full"]),
        tags=dict(type="list", elements="str"),
        ignore_warnings=dict(type="bool"),
        ignore_errors=dict(type="bool"),
    )
    argument_spec.update(checkpoint_argument_spec_for_commands)

    module = AnsibleModule(argument_spec=argument_spec)

    command = "add-data-center-query"

    result = api_command(module, command)
    module.exit_json(**result)


if __name__ == "__main__":
    main()
