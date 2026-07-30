#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: Contributors to the Ansible project
# Apache License, Version 2.0 (see LICENSE or https://www.apache.org/licenses/LICENSE-2.0)


from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: alpaca_command

short_description: Manage a single ALPACA Operator command via REST API

version_added: '1.0.0'

extends_documentation_fragment:
    - pcg.alpaca_operator.api_connection

description: >
    This Ansible module manages a single ALPACA Operator command. It provides fine-grained control over individual command properties.
    Use this module when you need to configure or modify one specific command, such as changing its timeout, toggling disabled, or setting a new schedule.
    Each command is uniquely identified by the combination of its name (description) and the assigned agentHostname.
    Note: Renaming a command or reassigning it to a different agent is not supported by this module, as these properties are used for identification.

    Update behavior:
    If the desired command already exists, only the fields required for unique identification need to be provided (i.e., either O(system.system_id) or O(system.system_name), and either O(command.agent_id) or O(command.agent_name).
    Any options not explicitly set in the module call or the playbook will retain their existing values from the current configuration.

options:
    system:
        description: Dictionary containing system identification. Either O(system.system_id) or O(system.system_name) must be provided.
        version_added: '1.0.0'
        required: true
        type: dict
        suboptions:
            system_id:
                description: Numeric ID of the target system. Optional if O(system.system_name) is provided.
                version_added: '2.0.0'
                required: false
                type: int
            system_name:
                description: Name of the target system. Optional if O(system.system_id) is provided.
                version_added: '2.0.0'
                required: false
                type: str
    command:
        description: Definition of the desired command. The definition can include fields such as O(command.name), O(command.agent_id) or O(command.agent_name), O(command.process_id), O(command.parameters), O(command.schedule), O(command.history), O(command.escalation), etc.
        version_added: '1.0.0'
        required: true
        type: dict
        suboptions:
            name:
                description: Name or description of the command.
                version_added: '1.0.0'
                required: false
                type: str
            state:
                description: Desired state of the command.
                version_added: '1.0.0'
                required: false
                type: str
                default: present
                choices: [present, absent]
            agent_id:
                description: >
                    Numeric ID of the agent. Optional if O(command.agent_name) is provided.
                    Note: This agent must also be assigned to the corresponding system if the system is managed via Ansible.
                version_added: '2.0.0'
                required: false
                type: int
            agent_name:
                description: >
                    Name of the agent. Optional if O(command.agent_id) is provided.
                    Note: This agent must also be assigned to the corresponding system if the system is managed via Ansible.
                version_added: '2.0.0'
                required: false
                type: str
            process_id:
                description: >
                    ID of the process to be executed. Optional if O(command.process_central_id) is provided.
                version_added: '2.0.0'
                required: false
                type: int
            process_central_id:
                description: >
                    Central ID / Global ID of the process to be executed. Optional if O(command.process_id) is provided.
                version_added: '2.0.0'
                required: false
                type: int
            parameters:
                description: Parameters for the process.
                version_added: '1.0.0'
                required: false
                type: str
            parameters_needed:
                description: Whether the execution of the command requires additional parameters.
                version_added: '2.0.0'
                required: false
                type: bool
            disabled:
                description: Whether the command is currently disabled.
                version_added: '1.0.0'
                required: false
                type: bool
            critical:
                description: Whether the command is marked as critical.
                version_added: '1.0.0'
                required: false
                type: bool
            schedule:
                description: Scheduling configuration.
                version_added: '1.0.0'
                required: false
                type: dict
                suboptions:
                    period:
                        description: Scheduling period.
                        version_added: '1.0.0'
                        type: str
                        required: false
                        choices: [every_5min, one_per_day, hourly, manually, fixed_time, hourly_with_mn, every_minute, even_hours_with_mn, odd_hours_with_mn, even_hours, odd_hours, fixed_time_once, fixed_time_immediate, cron_expression, disabled, start_fixed_time_and_hourly_mn]
                    time:
                        description: Execution time in HH:mm:ss. Required when O(command.schedule.period) is V(fixed_time), V(fixed_time_once), or V(start_fixed_time_and_hourly_mn).
                        version_added: '1.0.0'
                        type: str
                        required: false
                    cron_expression:
                        description: Quartz-compatible cron expression. Required when O(command.schedule.period) is V(cron_expression).
                        version_added: '2.0.0'
                        type: str
                        required: false
                    days_of_week:
                        description: List of weekdays for execution.
                        version_added: '2.0.0'
                        type: list
                        elements: str
                        required: false
                        choices: [monday, tuesday, wednesday, thursday, friday, saturday, sunday]
            history:
                description: Command history retention settings.
                version_added: '1.0.0'
                required: false
                type: dict
                suboptions:
                    document_all_runs:
                        description: Whether to document all executions.
                        version_added: '2.0.0'
                        type: bool
                        required: false
                    retention:
                        description: Retention time in seconds.
                        version_added: '1.0.0'
                        type: int
                        required: false
            auto_deploy:
                description: Whether to automatically deploy the command.
                version_added: '2.0.0'
                required: false
                type: bool
            timeout:
                description: Timeout configuration for command execution.
                version_added: '1.0.0'
                required: false
                type: dict
                suboptions:
                    type:
                        description: Type of timeout. Can be V(none), V(default), or V(custom).
                        version_added: '1.0.0'
                        type: str
                        required: false
                        choices: [none, default, custom]
                    value:
                        description: Timeout value in seconds (for V(custom) type).
                        version_added: '1.0.0'
                        type: int
                        required: false
            escalation:
                description: Escalation configuration.
                version_added: '1.0.0'
                required: false
                type: dict
                suboptions:
                    mail_enabled:
                        description: Whether email alerts are enabled.
                        version_added: '2.0.0'
                        type: bool
                        required: false
                    sms_enabled:
                        description: Whether SMS alerts are enabled.
                        version_added: '2.0.0'
                        type: bool
                        required: false
                    mail_address:
                        description: Email address for alerts.
                        version_added: '2.0.0'
                        type: str
                        required: false
                    sms_address:
                        description: SMS number for alerts.
                        version_added: '2.0.0'
                        type: str
                        required: false
                    min_failure_count:
                        description: Minimum number of failures before escalation.
                        version_added: '2.0.0'
                        type: int
                        required: false
                    triggers:
                        description: Trigger types for escalation.
                        version_added: '1.0.0'
                        type: dict
                        required: false
                        suboptions:
                            every_change:
                                description: Currently no description available
                                version_added: '2.0.0'
                                type: bool
                                required: false
                            to_red:
                                description: Currently no description available
                                version_added: '2.0.0'
                                type: bool
                                required: false
                            to_yellow:
                                description: Currently no description available
                                version_added: '2.0.0'
                                type: bool
                                required: false
                            to_green:
                                description: Currently no description available
                                version_added: '2.0.0'
                                type: bool
                                required: false

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
- name: Ensure a specific system command exist
  pcg.alpaca_operator.alpaca_command:
    system:
      system_name: system01
    command:
      name: "BKP: DB log sync"
      state: present
      agent_name: agent01
      parameters: "-p GLTarch -s <BKP_LOG_SRC> -l 4 -d <BKP_LOG_DEST1> -r <BKP_LOG_DEST2> -b <BKP_LOG_CLEANUP_INT> -t <BKP_LOG_CLEANUP_INT2> -h DB_HOST"
      process_id: 801
      schedule:
        period: manually
        time: "01:00:00"
        days_of_week:
          - monday
          - sunday
      parameters_needed: false
      disabled: false
      critical: true
      history:
        document_all_runs: true
        retention: 900
      auto_deploy: false
      timeout:
        type: default
        value: 30
      escalation:
        mail_enabled: true
        sms_enabled: true
        mail_address: "monitoring@pcg.io"
        sms_address: "0123456789"
        min_failure_count: 1
        triggers:
          every_change: true
          to_red: false
          to_yellow: false
          to_green: true
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"

- name: Delete a specific command
  pcg.alpaca_operator.alpaca_command:
  system:
      system_name: system01
  command:
      name: "BKP: DB log sync"
      agent_name: agent01
      state: absent
  api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"
'''

RETURN = r'''
msg:
    description: Status message describing what the module did
    version_added: '1.0.0'
    returned: always
    type: str
    sample: Command updated in system 42.

changed:
    description: Whether any changes were made
    version_added: '1.0.0'
    returned: always
    type: bool

changes:
    description: >
        Dictionary containing the differences between the current and desired command configuration.
        Only returned when a change is detected or would occur in check mode.
    version_added: '1.0.0'
    returned: when changes are detected (or would be applied in check_mode)
    type: dict
    contains:
        parameters:
            description: Changed parameters of the command (if any)
            version_added: '1.0.0'
            type: dict
            sample:
              current: "-p foo -s A -d B"
              desired: "-p foo -s A -d B -t X"
        schedule:
            description: Changed schedule section (if any)
            version_added: '1.0.0'
            type: dict
            sample:
              period:
                current: "manually"
                desired: "every_minute"
        escalation:
            description: Changed escalation section (if any)
            version_added: '1.0.0'
            type: dict
            sample:
              min_failure_count:
                current: 0
                desired: 1

payload:
    description: Full payload that would be sent to the API (in check_mode) or that was sent (when changed)
    version_added: '1.0.0'
    returned: when state is present and change occurred or would occur
    type: dict

command:
    description: Information about the deleted command
    version_added: '1.0.0'
    returned: when state=absent and command was deleted
    type: dict
    sample:
      id: 123
      name: "Backup Job"
      agentHostname: "agent-01"
'''

from ansible_collections.pcg.alpaca_operator.plugins.module_utils._alpaca_api import api_call, get_token, lookup_resource, lookup_processId, get_api_connection_argument_spec
from ansible.module_utils.basic import AnsibleModule


def build_payload(desired_command, system_command):
    """
    Constructs a configuration payload by prioritizing values from the desired configuration
    dictionary. If a value is not provided in the desired configuration, the function falls
    back to using the corresponding value from the existing configuration (if available).

    Parameters:
        desired_command (dict): A dictionary containing the desired configuration values.
        system_command (dict): A dictionary with existing configuration values.

    Returns:
        dict: A combined configuration payload dictionary.
    """
    payload = {
        "name":                 desired_command.get('name', None)                                                                                                                               if desired_command.get('name')                                                                                                                                              is not None else system_command.get('name', None),
        "agentId":              desired_command.get('agent_id', None)                                                                                                                           if desired_command.get('agent_id')                                                                                                                                          is not None else system_command.get('agentId', 0),
        "processId":            desired_command.get('process_id', None)                                                                                                                         if desired_command.get('process_id')                                                                                                                                        is not None else system_command.get('processId', 0),
        "parameters":           desired_command.get('parameters', None)                                                                                                                         if desired_command.get('parameters')                                                                                                                                        is not None else system_command.get('parameters', None),
        "schedule": {
            "period":           (desired_command.get('schedule') or {}).get('period', None)                                                                                                     if (desired_command.get('schedule') or {}).get('period', None)                                                                                                              is not None else (system_command.get('schedule') or {}).get('period', 'undefined'),
            "time":             (desired_command.get('schedule') or {}).get('time', None)                                                                                                       if (desired_command.get('schedule') or {}).get('time', None)                                                                                                                is not None else (system_command.get('schedule') or {}).get('time', None),
            "cronExpression":   (desired_command.get('schedule') or {}).get('cron_expression', None)                                                                                            if (desired_command.get('schedule') or {}).get('cron_expression', None) and (desired_command.get('schedule') or {}).get('period', None) == 'cron_expression'                            else (system_command.get('schedule') or {}).get('cronExpression', ''),
            "daysOfWeek":       sorted(
                                    (desired_command.get('schedule') or {}).get('days_of_week', [])                                                                                             if (desired_command.get('schedule') or {}).get('days_of_week', None)                                                                                                        is not None else (system_command.get('schedule') or {}).get('daysOfWeek', []),
                                    key=lambda x: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].index(x.lower())
                                )
        },
        "parametersNeeded":     desired_command.get('parameters_needed', None)                                                                                                                  if desired_command.get('parameters_needed')                                                                                                                                 is not None else system_command.get('parametersNeeded', True),
        "disabled":             desired_command.get('disabled', None)                                                                                                                           if desired_command.get('disabled')                                                                                                                                          is not None else system_command.get('disabled', True),
        "critical":             desired_command.get('critical', None)                                                                                                                           if desired_command.get('critical')                                                                                                                                          is not None else system_command.get('critical', True),
        "history": {
            "documentAllRuns":  (desired_command.get('history') or {}).get('document_all_runs', None)                                                                                           if (desired_command.get('history') or {}).get('document_all_runs', None)                                                                                                    is not None else (system_command.get('history') or {}).get('documentAllRuns', True),
            "retention":        (desired_command.get('history') or {}).get('retention', None)                                                                                                   if (desired_command.get('history') or {}).get('retention', None)                                                                                                            is not None else (system_command.get('history') or {}).get('retention', 0)
        },
        "autoDeploy":           desired_command.get('auto_deploy', None)                                                                                                                        if desired_command.get('auto_deploy')                                                                                                                                       is not None else system_command.get('autoDeploy', True),
        "timeout": {
            "type":             (desired_command.get('timeout') or {}).get('type', None).upper()                                                                                                if (desired_command.get('timeout') or {}).get('type', None)                                                                                                                 is not None else (system_command.get('timeout') or {}).get('type', 'None').upper(),
            "value":            (desired_command.get('timeout') or {}).get('value', None)                                                                                                       if (desired_command.get('timeout') or {}).get('value', None)                                                                                                                is not None else (system_command.get('timeout') or {}).get('value', 0)
        },
        "escalation": {
            "mailEnabled":      (desired_command.get('escalation') or {}).get('mail_enabled', None)                                                                                             if (desired_command.get('escalation') or {}).get('mail_enabled', None)                                                                                                      is not None else (system_command.get('escalation') or {}).get('mailEnabled', False),
            "smsEnabled":       (desired_command.get('escalation') or {}).get('sms_enabled', None)                                                                                              if (desired_command.get('escalation') or {}).get('sms_enabled', None)                                                                                                       is not None else (system_command.get('escalation') or {}).get('smsEnabled', False),
            "mailAddress":      (desired_command.get('escalation') or {}).get('mail_address', None)                                                                                             if (desired_command.get('escalation') or {}).get('mail_address', None)                                                                                                      is not None else (system_command.get('escalation') or {}).get('mailAddress', None),
            "smsAddress":       (desired_command.get('escalation') or {}).get('sms_address', None)                                                                                              if (desired_command.get('escalation') or {}).get('sms_address', None)                                                                                                       is not None else (system_command.get('escalation') or {}).get('smsAddress', None),
            "minFailureCount":  (desired_command.get('escalation') or {}).get('min_failure_count', None)                                                                                        if (desired_command.get('escalation') or {}).get('min_failure_count', None)                                                                                                 is not None else (system_command.get('escalation') or {}).get('minFailureCount', 0),
            "triggers": {
                "everyChange":  (desired_command.get('escalation') or {}).get('triggers', {}).get('every_change', None)                                                                         if (desired_command.get('escalation') or {}).get('triggers', {}).get('every_change', None)                                                                                  is not None else (system_command.get('escalation') or {}).get('triggers', {}).get('everyChange', True),
                "toRed":        (desired_command.get('escalation') or {}).get('triggers', {}).get('to_red', None)                                                                               if (desired_command.get('escalation') or {}).get('triggers', {}).get('to_red', None)                                                                                        is not None else (system_command.get('escalation') or {}).get('triggers', {}).get('toRed', True),
                "toYellow":     (desired_command.get('escalation') or {}).get('triggers', {}).get('to_yellow', None)                                                                            if (desired_command.get('escalation') or {}).get('triggers', {}).get('to_yellow', None)                                                                                     is not None else (system_command.get('escalation') or {}).get('triggers', {}).get('toYellow', True),
                "toGreen":      (desired_command.get('escalation') or {}).get('triggers', {}).get('to_green', None)                                                                             if (desired_command.get('escalation') or {}).get('triggers', {}).get('to_green', None)                                                                                      is not None else (system_command.get('escalation') or {}).get('triggers', {}).get('toGreen', True)
            }
        }
    }

    if (payload.get('timeout') or {}).get('type') == 'NONE' or (payload.get('timeout') or {}).get('type') == 'DEFAULT':
        payload['timeout']['value'] = None

    return payload


def main():
    module = AnsibleModule(
        argument_spec=dict(
            system=dict(
                type='dict',
                required=True,
                options=dict(
                    system_id=dict(type='int', required=False),
                    system_name=dict(type='str', required=False)
                )
            ),
            command=dict(
                type='dict',
                required=True,
                options=dict(
                    name=dict(type='str', required=False),
                    agent_id=dict(type='int', required=False),
                    agent_name=dict(type='str', required=False),
                    process_id=dict(type='int', required=False),
                    process_central_id=dict(type='int', required=False),
                    parameters=dict(type='str', required=False),
                    schedule=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            period=dict(type='str', required=False, choices=[
                                'every_5min', 'one_per_day', 'hourly', 'manually', 'fixed_time',
                                'hourly_with_mn', 'every_minute', 'even_hours_with_mn', 'odd_hours_with_mn',
                                'even_hours', 'odd_hours', 'fixed_time_once', 'fixed_time_immediate',
                                'cron_expression', 'disabled', 'start_fixed_time_and_hourly_mn'
                            ]),
                            time=dict(type='str', required=False),
                            cron_expression=dict(type='str', required=False),
                            days_of_week=dict(type='list', required=False, elements='str', choices=[
                                'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
                            ])
                        )
                    ),
                    parameters_needed=dict(type='bool', required=False),
                    disabled=dict(type='bool', required=False),
                    critical=dict(type='bool', required=False),
                    history=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            document_all_runs=dict(type='bool', required=False),
                            retention=dict(type='int', required=False)
                        )
                    ),
                    auto_deploy=dict(type='bool', required=False),
                    timeout=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            type=dict(type='str', required=False, choices=[
                                'none', 'default', 'custom'
                            ]),
                            value=dict(type='int', required=False)
                        )
                    ),
                    escalation=dict(
                        type='dict',
                        required=False,
                        options=dict(
                            mail_enabled=dict(type='bool', required=False),
                            sms_enabled=dict(type='bool', required=False),
                            mail_address=dict(type='str', required=False),
                            sms_address=dict(type='str', required=False),
                            min_failure_count=dict(type='int', required=False),
                            triggers=dict(
                                type='dict',
                                required=False,
                                options=dict(
                                    every_change=dict(type='bool', required=False),
                                    to_red=dict(type='bool', required=False),
                                    to_yellow=dict(type='bool', required=False),
                                    to_green=dict(type='bool', required=False)
                                )
                            )
                        )
                    ),
                    state=dict(type='str', required=False, default='present', choices=['present', 'absent'])
                )
            ),
            api_connection=get_api_connection_argument_spec()
        ),
        supports_check_mode=True,
    )

    api_url = "{0}://{1}:{2}/api".format(module.params['api_connection']['protocol'], module.params['api_connection']['host'], module.params['api_connection']['port'])
    token = get_token(api_url, module.params['api_connection']['username'], module.params['api_connection']['password'], module.params['api_connection']['tls_verify'])
    headers = {"Authorization": "Bearer {0}".format(token)}
    command_payload = None

    # Check if either a system ID or a system name is provided
    if not module.params.get('system', {}).get('system_name', None) and not module.params.get('system', {}).get('system_id', None):
        module.fail_json(msg="Either a system_name or system_id must be provided")

    # Resolve system id if needed
    if module.params.get('system', {}).get('system_name', None):
        system = lookup_resource(api_url, headers, "systems", "name", module.params['system']['system_name'], module.params['api_connection']['tls_verify'])
        if not system and module.params.get('command', {}).get('state') == "present":
            module.fail_json(msg="System '{0}' not found.".format(module.params['system']['system_name']))
        elif not system and module.params.get('command', {}).get('state') == "absent":
            module.exit_json(changed=False, msg="Command already absent because system was not found.")
        module.params['system']['system_id'] = system['id']

    # Check if system_id is valid
    if module.params.get('system', {}).get('system_id', None):
        system = lookup_resource(api_url, headers, "systems", "id", module.params['system']['system_id'], module.params['api_connection']['tls_verify'])
        if not system and module.params.get('command', {}).get('state') == "present":
            module.fail_json(msg="System with ID '{0}' not found. Please ensure system is created first.".format(module.params['system']['system_id']))
        elif not system and module.params.get('command', {}).get('state') == "absent":
            module.exit_json(changed=False, msg="Command already absent because system was not found.")

    # Check if either a agent ID or a agent name is provided
    if not module.params.get('command', {}).get('agent_name', None) and not module.params.get('command', {}).get('agent_id', None):
        module.fail_json(msg="Either agent_name or agent_id must be provided")

    # Resolve agent id if needed
    if module.params.get('command', {}).get('agent_name', None):
        agent = lookup_resource(api_url, headers, "agents", "hostname", module.params['command']['agent_name'], module.params['api_connection']['tls_verify'])
        if not agent and module.params.get('command', {}).get('state') == "present":
            module.fail_json(msg="Agent '{0}' not found.".format(module.params['command']['agent_name']))
        elif not agent and module.params.get('command', {}).get('state') == "absent":
            module.exit_json(changed=False, msg="Command already absent because agent was not found.")
        module.params['command']['agent_id'] = agent['id']

    # Check if agent_id is valid
    if module.params.get('command', {}).get('agent_id', None):
        agent = lookup_resource(api_url, headers, "agents", "id", module.params['command']['agent_id'], module.params['api_connection']['tls_verify'])
        if not agent and module.params.get('command', {}).get('state') == "present":
            module.fail_json(msg="Agent with ID '{0}' not found. Please ensure agent is created first.".format(module.params['command']['agent_id']))
        elif not agent and module.params.get('command', {}).get('state') == "absent":
            module.exit_json(changed=False, msg="Command already absent because agent was not found.")

    # Check if either a process ID or the processes central ID is provided
    if not module.params.get('command', {}).get('process_central_id', None) and not module.params.get('command', {}).get('process_id', None) and module.params.get('command', {}).get('state') == "present":
        module.fail_json(msg="Either process_central_id or process_id must be provided")

    # Resolve process_id if needed
    if module.params.get('command', {}).get('process_central_id', None) and not module.params.get('command', {}).get('process_id', None) and module.params.get('command', {}).get('state') == "present":
        process_id = lookup_processId(api_url, headers, "globalId", module.params.get('command', {}).get('process_central_id'), module.params['api_connection']['tls_verify'],)
        if not process_id:
            module.fail_json(msg="Process ID lookup for Central ID '{0}' not found".format(module.params['command']['process_central_id']))
        module.params['command']['process_id'] = process_id

    # Get currently configured system commands
    system_commands = api_call("GET", "{0}/systems/{1}/commands".format(api_url, module.params['system']['system_id']), headers=headers, verify=module.params['api_connection']['tls_verify']).json()

    # Check, if command already exists using a combination of 'agentHostname' and 'name' for a comparison (the description field of the command in the ALPACA Operator UI) for the identification
    if system_commands:
        for system_command in system_commands:
            if system_command.get('name', None) == module.params.get('command', {}).get('name', None) and system_command.get('agentHostname', None) == agent.get('hostname', None):
                system_command = api_call("GET", "{0}/systems/{1}/commands/{2}".format(api_url, module.params['system']['system_id'], system_command.get('id', None)), headers=headers, verify=module.params['api_connection']['tls_verify']).json()
                if not system_command:
                    module.fail_json(msg="Failed to retrieve command details of command ID '{0}' in system ID '{1}'".format(module.params['command']['agent_id'], module.params['system']['system_id']))
                break
            else:
                system_command = {}
    else:
        system_command = {}

    if module.params['command']['state'] == 'present':
        command_payload = build_payload(module.params.get('command', {}), system_command)

        if system_command:
            # Compare current command configuration with the desired command configuration if it already exists
            diff = {}
            for key in command_payload:
                if key not in ['schedule', 'history', 'escalation', 'timeout']:
                    if command_payload.get(key, None) != system_command.get(key, None):
                        diff[key] = {
                            'current': system_command.get(key, None),
                            'desired': command_payload.get(key, None)
                        }
                if key in ['schedule', 'history', 'escalation', 'timeout']:
                    for sub_key in command_payload.get(key, {}):
                        if sub_key not in ['triggers']:
                            if (command_payload.get(key) or {}).get(sub_key, None) != (system_command.get(key) or {}).get(sub_key, None):
                                if key not in diff:
                                    diff[key] = {}
                                diff[key][sub_key] = {
                                    'current': (system_command.get(key) or {}).get(sub_key, None),
                                    'desired': (command_payload.get(key) or {}).get(sub_key, None)
                                }
                        if sub_key in ['triggers']:
                            for sub_sub_key in (command_payload.get(key) or {}).get(sub_key, {}):
                                if ((command_payload.get(key) or {}).get(sub_key) or {}).get(sub_sub_key, {}) != ((system_command.get(key) or {}).get(sub_key) or {}).get(sub_sub_key, None):
                                    if key not in diff:
                                        diff[key] = {}
                                    if sub_key not in diff.get(key, {}):
                                        diff[key][sub_key] = {}
                                    diff[key][sub_key][sub_sub_key] = {
                                        'current': ((system_command.get(key) or {}).get(sub_key) or {}).get(sub_sub_key, None),
                                        'desired': ((command_payload.get(key) or {}).get(sub_key) or {}).get(sub_sub_key, None)
                                    }

            if diff:
                if module.check_mode:
                    module.exit_json(changed=True, msg="Command would be updated in system {0}.".format(module.params['system']['system_id']), changes=diff, payload=command_payload)

                # Update command
                api_call("PUT", "{0}/systems/{1}/commands/{2}".format(api_url, module.params['system']['system_id'], system_command['id']), headers=headers, json=command_payload, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to update command")
                module.exit_json(changed=True, msg="Command updated in system {0}.".format(module.params['system']['system_id']), changes=diff)

            module.exit_json(changed=False, msg="Command already exists with the desired configuration in system {0}.".format(module.params['system']['system_id']))

        # Create command if it does not exist already
        if module.check_mode:
            module.exit_json(changed=True, msg="Command would be created in system {0}.".format(module.params['system']['system_id']), payload=command_payload)

        api_call("POST", "{0}/systems/{1}/commands".format(api_url, module.params['system']['system_id']), headers=headers, json=command_payload, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to create command")
        module.exit_json(changed=True, msg="Command created in system {0}.".format(module.params['system']['system_id']), payload=command_payload)

    elif module.params['command']['state'] == 'absent':
        if system_command:
            if module.check_mode:
                module.exit_json(changed=True, msg="Command would be deleted from system {0}.".format(module.params['system']['system_id']), payload=command_payload)

            # Delete command
            api_call("DELETE", "{0}/systems/{1}/commands/{2}".format(api_url, module.params['system']['system_id'], system_command['id']), headers=headers, verify=module.params['api_connection']['tls_verify'], module=module, fail_msg="Failed to update command")
            module.exit_json(changed=True, msg="Command delete from system {0}.".format(module.params['system']['system_id']), command=system_command)

        module.exit_json(changed=False, msg="Command already absent.")

    module.exit_json(changed=False, msg="Command state processed.")


if __name__ == '__main__':
    main()
