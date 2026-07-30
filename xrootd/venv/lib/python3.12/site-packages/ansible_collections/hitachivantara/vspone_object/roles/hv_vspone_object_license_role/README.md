# hv_vspone_object_license_role

An Ansible role to set a serial number and upload a license file on Hitachi VSP One Object.

## Overview

This role:

1. Validates the required inputs.
2. Sets the serial number by using `hitachivantara.vspone_object.oneobject_node.hv_serial_number`.
3. Uploads the license file by using `hitachivantara.vspone_object.oneobject_node.hv_license`.
4. Retrieves the current serial number and license details by using `hitachivantara.vspone_object.oneobject_node.hv_serial_number_facts` and `hitachivantara.vspone_object.oneobject_node.hv_licenses_facts`.
5. Fails the role if a required step fails.

## Requirements

- Ansible 2.9+
- `hitachivantara.vspone_object` collection (`>=1.0.0`)

## Role Variables

Required variable:

```yaml
connection_info:
  http_request_timeout: 300
  http_request_retry_times: 3
  http_request_retry_interval_seconds: 5
  ssl:
    validate_certs: false
  cluster_name: your_cluster_name
  region: your_region
  oneobject_node_username: your_username
  oneobject_node_userpass: your_password
  oneobject_node_client_id: vsp-object-external-client
```

Role inputs:

```yaml
hv_vspone_object_license_role_serial_number: "S12345678"
hv_vspone_object_license_role_file_path: "/path/to/license_file.txt"
```

Role output facts:

- `hv_vspone_object_license_role_serial_set_result`: serial number set task result.
- `hv_vspone_object_license_role_upload_result`: license upload task result.
- `hv_vspone_object_license_role_serial_number_facts_result`: serial number facts task result.
- `hv_vspone_object_license_role_facts_result`: license facts task result.
- `hv_vspone_object_license_role_serial_number_facts`: discovered serial number details.
- `hv_vspone_object_license_role_facts`: discovered license details.

## Example Playbook

```yaml
- name: Set serial number and upload license
  hosts: localhost
  gather_facts: false
  roles:
    - role: hv_vspone_object_license_role
      vars:
        connection_info: "{{ connection_info }}"
        hv_vspone_object_license_role_serial_number: "S12345678"
        hv_vspone_object_license_role_file_path: "/path/to/license_file.txt"
```

## License

Apache License 2.0
