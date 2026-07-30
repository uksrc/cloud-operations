# hv_vspone_object_storage_component_role

An Ansible role to run storage component operations in Hitachi VSP One Object:

- Activate one or more storage components by ID.
- Optionally evaluate component capacities against a warn threshold.

## Overview

This role:

1. Requires `connection_info`.
2. Requires at least one role input:
  - non-empty `hv_vspone_object_storage_component_role_ids`, or
  - `hv_vspone_object_storage_component_used_capacity_bytes_gt`.
3. Validates `hv_vspone_object_storage_component_role_ids` as a non-empty list when provided.
4. If IDs are provided, attempts activation per ID and continues even if one or more activations fail (`ignore_errors: true`).
5. If IDs are provided, builds and exposes activation summary facts (`total`, `success`, `failed`, `failures`).
6. If warn threshold is provided, fetches CAPACITY facts, excludes `aggregate`, and lists components where `used_bytes` is greater than the provided threshold.

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

Optional role inputs (provide at least one):

```yaml
hv_vspone_object_storage_component_role_ids:
  - 123456789
  - 987654321

# Optional threshold in bytes.
# The role compares used_bytes against this provided value.
hv_vspone_object_storage_component_used_capacity_bytes_gt: 5000000000
```

Role output facts:

- `hv_vspone_object_storage_component_role_activation_result`: raw looped module result (set when IDs are provided).
- `hv_vspone_object_storage_component_role_summary`: summary with total, success, failed, and failures (set when IDs are provided).
- `hv_vspone_object_storage_component_role_capacity_result`: raw capacity facts result (`query: CAPACITY`) (set when warn threshold is provided).
- `hv_vspone_object_storage_component_role_warned_capacities`: filtered list where `used_bytes` is above the provided threshold (set when warn threshold is provided).
- `hv_vspone_object_storage_component_role_exceeded_ids`: list of `storage_component_id` values where `used_bytes` is above the provided threshold (set when warn threshold is provided).
- `hv_vspone_object_storage_component_role_exceeded_count`: number of components where `used_bytes` is above the provided threshold (set when warn threshold is provided).

## Example Playbook

```yaml
- name: Run storage component role workflow
  hosts: localhost
  gather_facts: false
  roles:
    - role: hv_vspone_object_storage_component_role
      vars:
        connection_info: "{{ connection_info }}"
        hv_vspone_object_storage_component_role_ids:
          - 123456789
          - 987654321
        hv_vspone_object_storage_component_used_capacity_bytes_gt: 5000000000
```

## License

Apache License 2.0
