# RAL OpenStack VM module

A module to provision a VM in the STFC Cloud environment (aka RAL).

## Input variables

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `image_name` | string | `ubuntu-noble-24.04-nogui` | OpenStack image name; the most recent matching image is used. |
| `flavour` | string | `l3.nano` | OpenStack compute flavour name. |
| `network` | string | `UKSRC-Network` | OpenStack network name. |
| `primary_user` | string | Required | Username created by cloud-init and used to connect with Ansible. |
| `primary_user_ssh_key` | string | Required | SSH public key for the primary user. |
| `network_cidr` | string | `192.168.64.0/22` | CIDR used to select the subnet and passed to Ansible as `NETWORK_CIDR`. |
| `fixed_ip` | string | Required | Fixed IP address for the VM on the selected subnet. |
| `floating_ip` | string | Required | Existing floating IP address to associate with the VM port. |
| `additional_dependencies` | bool | `false` | Whether to run the optional dependency provisioning step. |
| `ansible_dir` | string | `null` | Caller Ansible directory; defaults to `../ansible` relative to the root Terraform module. Relative overrides are resolved from Terraform's working directory. |

The module also reads `cloud-config.yaml.tpl` from Terraform's working
directory, passing it `primary_user` and `primary_key`.

## Ansible provisioning

Terraform runs Ansible locally, in this order: system update, optional
dependencies, user management, and opkssh setup. The system update waits 60
seconds before starting. The machine running Terraform needs Bash,
`ansible-playbook`, the required Ansible collections, network access to the
instance's `access_ip_v4`, and the private key corresponding to
`primary_user_ssh_key`. Playbooks must target the supplied host and perform any
necessary privilege escalation. Ansible host key checking is disabled by the
module.

The module supplies `ansible/update_system.yml`, `ansible/manage_users.yml`,
and `ansible/add_opkssh.yml`. They use the shared roles in
`common/ansible/roles`; keep that directory at its current relative location
to the module. The caller supplies configuration in `ansible_dir`, which is
also the working directory for each playbook:

| Path | Assumption |
| --- | --- |
| `group_vars/all/system.yml` | Required variables for the system update playbook, including `slack_webhook_url` on Ubuntu. |
| `group_vars/all/users.yml` | Required variables for user management and opkssh, including `additional_users` (which may be an empty list). See the [manage_users role](../../../ansible/roles/manage_users/README.md) for the user fields. |
| `.env` | Optional Bash file sourced and exported before each playbook. |
| `dependencies.yml` | Caller-provided playbook, required when `additional_dependencies` is true. It must target the supplied host and perform any required privilege escalation. |
| `roles/` | Optional caller-specific roles, available to the dependency playbook. |

The module adds the shared and caller role directories to
`ANSIBLE_ROLES_PATH`, followed by any existing value from the environment or
`.env`. The standard playbooks load the caller's variable files explicitly.
Terraform tracks changes to each standard playbook, its shared role and its
variable file; `.env` changes trigger the system update step. The dependency
step tracks `dependencies.yml` and files under the caller's `roles/` directory.
Changes to files referenced by the dependency playbook outside these paths are
not tracked automatically.

