# hv_vspone_object_certificate_upload_role

An Ansible role to upload all certificate files from a folder to Hitachi VSP One Object by using the `hitachivantara.vspone_object.oneobject_node.hv_certificates` module.

## Overview

This role:

1. Reads all files from `hv_vspone_object_certificate_upload_role_folder_path`.
2. Tries to add each file as a certificate using `hv_certificates`.

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

Optional variable:

```yaml
# Folder containing certificate files to upload
hv_vspone_object_certificate_upload_role_folder_path: "/path/to/certificate-folder"
```

Role output:

- `hv_vspone_object_certificate_upload_role_result`: raw looped module result.

## Example Playbook

```yaml
- name: Upload certificates from folder
  hosts: localhost
  gather_facts: false
  roles:
    - role: hv_vspone_object_certificate_upload_role
      vars:
        connection_info: "{{ connection_info }}"
        hv_vspone_object_certificate_upload_role_folder_path: "/path/to/certificate-folder"
```

## License

Apache License 2.0
