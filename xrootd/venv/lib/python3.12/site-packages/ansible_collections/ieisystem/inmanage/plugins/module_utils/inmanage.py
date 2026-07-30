# -*- coding:utf-8 -*-
# Copyright(C) 2023 IEIT Inc. All Rights Reserved.

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

import sys
try:
    import inmanage
    inmanage_msg = ''
    inmanage_temp = True
except ImportError as e:
    if sys.version_info.major == 2:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        inmanage_msg = str(exc_value)
    else:
        inmanage_msg = e.msg
    inmanage_temp = False
from ansible.module_utils.basic import env_fallback

inmanage_provider_spec = {
    'host': dict(type='str'),
    'username': dict(type='str', fallback=(env_fallback, ['ANSIBLE_NET_USERNAME'])),
    'password': dict(type='str', fallback=(env_fallback, ['ANSIBLE_NET_PASSWORD']), no_log=True),
}
inmanage_argument_spec = {
    'provider': dict(type='dict', options=inmanage_provider_spec),
}
inmanage_top_spec = {
    'host': dict(type='str'),
    'username': dict(type='str'),
    'password': dict(type='str', no_log=True),
}
inmanage_argument_spec.update(inmanage_top_spec)


def load_params(module):
    """load_params"""
    provider = module.params.get('provider') or dict()
    for key, value in provider.items():
        if key in inmanage_argument_spec:
            if module.params.get(key) is None and value is not None:
                module.params[key] = value


def get_connection(module):
    """get_connection"""
    load_params(module)
    # result = dict()
    # if module.check_mode:
    #     result['changed'] = True
    #     result['state'] = 'Success'
    #     result['message'] = module.params['subcommand']
    # else:
    dict_param = module.params
    if not inmanage_temp:
        module.fail_json(msg='inmanage_sdk must be installed to use this module.' + inmanage_msg)
    result = inmanage.main(dict_param)
    return result
