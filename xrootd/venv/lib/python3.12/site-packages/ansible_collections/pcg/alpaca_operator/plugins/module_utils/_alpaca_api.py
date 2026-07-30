# -*- coding: utf-8 -*-

# Copyright: Contributors to the Ansible project
# Apache License, Version 2.0 (see LICENSE or https://www.apache.org/licenses/LICENSE-2.0)


# This module is for internal use only within the pcg.alpaca_operator collection.
# Python versions supported: 3.8+

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

import json as json_module

from ansible.module_utils.urls import open_url


def api_call(method, url, headers=None, json=None, verify=True, module=None, fail_msg=None):
    """Make API call and return response data"""
    try:
        data = None
        if json is not None:
            data = json_module.dumps(json).encode('utf-8')
            if headers is None:
                headers = {}
            else:
                headers = dict(headers)  # Create a copy to avoid modifying the original
            headers['Content-Type'] = 'application/json'

        response = open_url(
            url,
            method=method,
            headers=headers,
            data=data,
            validate_certs=verify,
            http_agent='ansible-alpaca-operator'
        )

        status_code = response.getcode()
        content = response.read()
        text = content.decode('utf-8') if isinstance(content, bytes) else content

        if status_code >= 400:
            if module and fail_msg:
                module.fail_json(msg="{0}: {1}".format(fail_msg, text))
            raise Exception("HTTP {0}: {1}".format(status_code, text))

        # Parse JSON if content exists, otherwise return empty dict
        try:
            json_result = json_module.loads(text) if text else {}
        except ValueError:
            json_result = {}

        class ResponseDict(dict):
            """Dictionary-like object with json() method and attribute access for compatibility"""
            def __init__(self, status_code, text, json_data):
                # Only initialize dict with json_data if it's a dict, otherwise store as attribute
                if isinstance(json_data, dict):
                    super(ResponseDict, self).__init__(json_data)
                else:
                    super(ResponseDict, self).__init__()
                self._status_code = status_code
                self._text = text
                self._json_data = json_data

            def json(self):
                """Return the parsed JSON data (can be dict, list, or other types)"""
                return self._json_data

            def __getattr__(self, name):
                """Allow attribute access to status_code, text, and dictionary keys"""
                if name == 'status_code':
                    return self._status_code
                elif name == 'text':
                    return self._text
                try:
                    return self[name]
                except KeyError:
                    raise AttributeError("'{0}' object has no attribute '{1}'".format(self.__class__.__name__, name))

        result = ResponseDict(status_code, text, json_result)
        return result

    except Exception as e:
        if module:
            error_msg = "{0}: {1}".format(fail_msg or 'API request failed.', str(e))
            module.fail_json(msg=error_msg)
        raise


def get_token(api_url, username, password, verify):
    """Get API token"""
    payload = {"username": username, "password": password}
    response = api_call("POST", "{0}/auth/login".format(api_url), json=payload, verify=verify)
    return response.json()["token"]


def lookup_resource(api_url, headers, resource, key, value, verify):
    """Find resource by the given key and value"""
    response = api_call("GET", "{0}/{1}".format(api_url, resource), headers=headers, verify=verify)
    for resource in response.json():
        if resource.get(key) == value:
            return resource
    return None


def lookup_processId(api_url, headers, key, value, verify):
    """Find processId by the given key and value"""
    response = api_call("GET", "{0}/processes/tree".format(api_url), headers=headers, verify=verify)
    for type in response.json():
        for process in type.get('processes', []):
            if str(process.get(key)) == str(value):
                return process.get('id')
    return None


def get_api_connection_argument_spec():
    """Return the argument spec for api_connection parameter"""
    return dict(
        type='dict',
        required=True,
        options=dict(
            host=dict(type='str', required=False, default='localhost'),
            port=dict(type='int', required=False, default='8443'),
            protocol=dict(type='str', required=False, default='https', choices=['http', 'https']),
            username=dict(type='str', required=True, no_log=True),
            password=dict(type='str', required=True, no_log=True),
            tls_verify=dict(type='bool', required=False, default=True)
        )
    )
