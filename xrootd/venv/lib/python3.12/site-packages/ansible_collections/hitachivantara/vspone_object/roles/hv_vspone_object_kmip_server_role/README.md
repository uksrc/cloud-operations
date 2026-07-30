# hv_vspone_object_kmip_server_role

An Ansible role to update the HTTPS cipher string for one or more existing KMIP servers in Hitachi VSP One Object.

## Overview

This role:

1. Accepts a list of KMIP server names and one HTTPS cipher string.
2. Tries to fetch each server by using `hitachivantara.vspone_object.oneobject_node.hv_kmip_server_facts`.
3. Uses fetched server details and updates only the `https_ciphers` value by using `hitachivantara.vspone_object.oneobject_node.hv_kmip` with `state: modify`.
4. Continues to the next server if fetch or update fails.
5. Exposes a summary fact with success and failure counts.

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
hv_vspone_object_kmip_server_role_names:
  - sample_kmip_server_1
  - sample_kmip_server_2

hv_vspone_object_kmip_server_role_https_ciphers: "TLS_RSA_WITH_AES_128_CBC_SHA256,TLS_AES_256_GCM_SHA384"
```

Role output facts:

- `hv_vspone_object_kmip_server_role_fetch_result`: raw looped fetch result.
- `hv_vspone_object_kmip_server_role_update_result`: raw looped update result.
- `hv_vspone_object_kmip_server_role_summary`: summary with requested, fetch and update counts, and failure details.

## Example Playbook

```yaml
- name: Update HTTPS ciphers for KMIP servers
  hosts: localhost
  gather_facts: false
  roles:
    - role: hv_vspone_object_kmip_server_role
      vars:
        connection_info: "{{ connection_info }}"
        hv_vspone_object_kmip_server_role_names:
          - sample_kmip_server_1
          - sample_kmip_server_2
        hv_vspone_object_kmip_server_role_https_ciphers: "TLS_RSA_WITH_AES_128_CBC_SHA256,TLS_AES_256_GCM_SHA384"
```

## License

Apache License 2.0
