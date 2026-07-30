# -*- coding: utf-8 -*-

# Copyright: Contributors to the Ansible project
# Apache License, Version 2.0 (see LICENSE or https://www.apache.org/licenses/LICENSE-2.0)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


class ModuleDocFragment(object):
    DOCUMENTATION = r'''
---
options:
    api_connection:
        description: Connection details for accessing the ALPACA Operator API.
        version_added: '2.0.0'
        required: true
        type: dict
        suboptions:
            username:
                description: Username for authentication against the ALPACA Operator API.
                version_added: '1.0.0'
                required: true
                type: str
            password:
                description: Password for authentication against the ALPACA Operator API.
                version_added: '1.0.0'
                required: true
                type: str
            protocol:
                description: Protocol to use. Can be V(http) or V(https).
                version_added: '1.0.0'
                required: false
                default: https
                choices: [http, https]
                type: str
            host:
                description: Hostname of the ALPACA Operator server.
                version_added: '1.0.0'
                required: false
                default: localhost
                type: str
            port:
                description: Port of the ALPACA Operator API.
                version_added: '1.0.0'
                required: false
                default: 8443
                type: int
            tls_verify:
                description: Validate SSL certificates.
                version_added: '1.0.0'
                required: false
                default: true
                type: bool
'''
