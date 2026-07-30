# ALPACA Operator Collection for Ansible

[![CI](https://github.com/pcg-sap/alpaca-operator-ansible/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/pcg-sap/alpaca-operator-ansible/actions/workflows/ci-cd.yml)

This Ansible Collection provides modules to manage **[ALPACA Operator](https://alpaca.pcg.io/)** via its REST API. It is designed to allow automation of common lifecycle operations related to groups, agents, systems, and commands within ALPACA-managed infrastructures.

## License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details.


## Code of Conduct

We follow the [Ansible Code of Conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html) in all our interactions within this project.

If you encounter abusive behavior, please refer to the [policy violations](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html#policy-violations) section of the Code for information on how to raise a complaint.

## Included content

This collection includes the following modules:

| Module Name                           | Description                                              |
| ------------------------------------- | -------------------------------------------------------- |
| `pcg.alpaca_operator.alpaca_agent`       | Manage ALPACA Operator agents                            |
| `pcg.alpaca_operator.alpaca_command_set` | Manage all ALPACA Operator commands of a specific system |
| `pcg.alpaca_operator.alpaca_command`     | Manage a single ALPACA Operator command                  |
| `pcg.alpaca_operator.alpaca_group`       | Manage ALPACA Operator groups                            |
| `pcg.alpaca_operator.alpaca_system`      | Manage ALPACA Operator systems                           |


All modules require API connection parameters and support both `present` and `absent` states where applicable.

Additionally, a shared utility (`_alpaca_api.py`) is available under `module_utils` for internal use, handling REST API logic and token management.

## Requirements

- Python >= 3.9
- ansible-core >= 2.12
- ALPACA Operator >= 5.6.0

### Support Matrix

<!-- support-matrix:start -->

|             | Ansible 2.12.* | Ansible 2.13.* | Ansible 2.14.* | Ansible 2.15.* | Ansible 2.16.* | Ansible 2.17.* | Ansible 2.18.* | Ansible 2.19.* | Ansible 2.20.* |
| ----------- | -------------- | -------------- | -------------- | -------------- | -------------- | -------------- | -------------- | -------------- | -------------- |
| Python 3.8 | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Python 3.9 | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Python 3.10 | ⬜ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ | ⬜ | ⬜ |
| Python 3.11 | ⬜ | ⬜ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ |
| Python 3.12 | ⬜ | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Python 3.13 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ✅ |
| Python 3.14 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |

<!-- support-matrix:end -->

### Legend

| Symbol | Meaning                                               |
| ------ | ----------------------------------------------------- |
| ✅     | Tested and **supported**                              |
| ❌     | Tested and **unsupported** (failed)                   |
| ⬜     | **Not tested** (e.g. unsupported version combination) |

## Installation

You can install this collection from Ansible Galaxy:

```bash
ansible-galaxy collection install pcg.alpaca_operator
```

Or directly from the Git repository:

```bash
ansible-galaxy collection install git+https://github.com/pcg-sap/alpaca-operator-ansible.git
```

Alternatively, you can install manually from a release:

1. Download the latest release from [GitHub Releases](https://github.com/pcg-sap/alpaca-operator-ansible/releases)
2. Copy the release archive to your server
3. Extract the archive
4. Change to the extracted directory
5. Install the collection:

```bash
cd alpaca-operator-ansible-*
ansible-galaxy collection install ./ --force
```

### Quick Start Guide

For a complete setup guide including Ansible installation, collection setup, and first playbook execution, see the [Quick Start Guide](docs/index.md).

## Example Usage

### Group Management

```yaml
- name: Ensure group "ansible_testing_group_01" exists
  pcg.alpaca_operator.alpaca_group:
    name: ansible_testing_group_01
    state: present
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"

- name: Delete group ansible_testing_group_01
  pcg.alpaca_operator.alpaca_group:
    name: ansible_testing_group_01
    state: absent
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"
```

### Agent Management

```yaml
- name: Ensure agent "ansible_testing_agent_01" exists
  pcg.alpaca_operator.alpaca_agent:
    name: ansible_testing_agent_01
    description: My Test Agent 01
    ip_address: 10.1.1.1
    location: virtual
    escalation:
      failures_before_report: 1
      mail_enabled: False
      mail_address: monitoring_1@pcg.io
      sms_enabled: True
      sms_address: 0123456789
    script_group_id: -1
    state: present
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"

- name: Delete agent ansible_testing_agent_01
  pcg.alpaca_operator.alpaca_agent:
    name: ansible_testing_agent_01
    state: absent
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"
```

### System Management

```yaml
- name: Ensure system "ansible01" exists
  pcg.alpaca_operator.alpaca_system:
    name: ansible01
    description: Ansible Test System 01
    magic_number: 59
    checks_disabled: False
    group_name: ansible_testing_group_01
    rfc_connection:
      type: instance
      host: ansible01-host
      instance_number: 42
      sid: ABC
      logon_group: ansible01-lgroup
      username: rfc_myUser
      password: rfc_myPasswd
      client: 123
      sap_router_string: rfc_SAPRouter
      snc_enabled: False
    agents:
      - name: ansible_testing_agent_01
      - name: ansible_testing_agent_02
      - name: ansible_testing_agent_03
    variables:
      - name: <BKP_DATA_CLEANUP_INT>
        value: "400"
      - name: <BKP_DATA_DEST1>
        value: this is a string
      - name: <BKP_DATA_DEST2>
        value: "11"
    state: present
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"

- name: Delete system ansible01
  pcg.alpaca_operator.alpaca_system:
    name: ansible01
    state: absent
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"
```

### System Command Management

> [!WARNING]
> When using the `pcg.alpaca_operator.alpaca_command_set` module, all existing commands on the target system that are not included in your playbook will be deleted. Use this module with care!

```yaml
- name: Ensure that exactly these system commands exist — no more, no fewer
  pcg.alpaca_operator.alpaca_command_set:
    system:
      system_name: ansible01
    commands:
      - name: "BKP: DB log sync 1"
        state: present
        agent_name: ansible_testing_agent_01
        parameters: "-p GLTarch -s <BKP_LOG_SRC> -l 4 -d <BKP_LOG_DEST1> -r <BKP_LOG_DEST2> -b <BKP_LOG_CLEANUP_INT> -t <BKP_LOG_CLEANUP_INT2> -h DB_HOST"
        process_central_id: 8990048
        schedule:
          period: manually
          time: "11:11:11"
          cron_expression: ""
          days_of_week:
            - monday
            - sunday
        parameters_needed: false
        disabled: true
        critical: true
        history:
          document_all_runs: false
          retention: 100
        auto_deploy: false
        timeout:
          type: custom
          value: 10
        escalation:
          mail_enabled: true
          sms_enabled: true
          mail_address: "monitoring_1@pcg.io"
          sms_address: "0123456789-1"
          min_failure_count: 1
          triggers:
            every_change: true
            to_red: false
            to_yellow: false
            to_green: true
      - name: "BKP: DB log sync 2"
        state: present
        agent_name: ansible_testing_agent_02
        parameters: "-p GLTarch -s <BKP_LOG_SRC> -l 4 -d <BKP_LOG_DEST1> -r <BKP_LOG_DEST2> -b <BKP_LOG_CLEANUP_INT> -t <BKP_LOG_CLEANUP_INT2> -h DB_HOST"
        process_id: 801
        schedule:
          period: manually
          time: "12:12:12"
          cron_expression: ""
          days_of_week:
            - monday
            - wednesday
            - friday
            - sunday
        parameters_needed: false
        disabled: true
        critical: true
        history:
          document_all_runs: false
          retention: 200
        auto_deploy: false
        timeout:
          type: custom
          value: 20
        escalation:
          mail_enabled: true
          sms_enabled: true
          mail_address: "monitoring_2@pcg.io"
          sms_address: "0123456789-2"
          min_failure_count: 2
          triggers:
            every_change: true
            to_red: false
            to_yellow: false
            to_green: true

- name: Ensure a specific system command exist
  pcg.alpaca_operator.alpaca_command:
    system:
      system_name: ansible01
    command:
      name: "BKP: DB log sync 3"
      state: present
      agent_name: ansible_testing_agent_03
      parameters: "-p GLTarch -s <BKP_LOG_SRC> -l 4 -d <BKP_LOG_DEST1> -r <BKP_LOG_DEST2> -b <BKP_LOG_CLEANUP_INT> -t <BKP_LOG_CLEANUP_INT2> -h DB_HOST"
      process_id: 801
      process_central_id: 8990048
      schedule:
        period: manually
        time: "13:13:13"
        cron_expression: ""
        days_of_week:
          - monday
          - sunday
          - wednesday
      parameters_needed: false
      disabled: true
      critical: true
      history:
        document_all_runs: false
        retention: 300
      auto_deploy: false
        timeout:
          type: custom
          value: 30
      escalation:
        mail_enabled: true
        sms_enabled: true
        mail_address: "monitoring_3@pcg.io"
        sms_address: "0123456789-3"
        min_failure_count: 3
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

- name: Delete all commands in system ansible01
  pcg.alpaca_operator.alpaca_command_set:
    system:
      system_name: ansible01
    commands: []
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
      system_name: ansible01
    command:
      name: "BKP: DB log sync 3"
      agent_name: "ansible_testing_agent_03"
      state: absent
    api_connection:
      host: "{{ ALPACA_Operator_API_Host }}"
      protocol: "{{ ALPACA_Operator_API_Protocol }}"
      port: "{{ ALPACA_Operator_API_Port }}"
      username: "{{ ALPACA_Operator_API_Username }}"
      password: "{{ ALPACA_Operator_API_Password }}"
      tls_verify: "{{ ALPACA_Operator_API_Validate_Certs }}"
```