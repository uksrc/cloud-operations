# User Management Migration Guide

## Overview

User management has been split between Terraform and Ansible:

- **OpenTofu**: Creates only the primary user - runs the Ansible script
- **Ansible**: Manages all additional users (no VM recreation needed)

## OpenTofu (`tf/host_user.auto.tfvars`)

```hcl
primary_user = "ubuntu"
primary_user_ssh_key = "ssh-rsa AAAAB3..."
```

### Ansible (`ansible/group_vars/all/users.yml`)

**New structure:**

```yaml
additional_users:
  alice: "ssh-rsa AAAAB3..."
  bob: "ssh-rsa AAAAB3..."
```

**Note:** User details are kept in `users.yml` (which is gitignored). Copy from `users.yml.example` template.

## Adding Ansible-Managed Users

### 1. Move additional users to Ansible

Edit `ansible/group_vars/all/users.yml` (not the `users.yml.example` file):

```yaml
additional_users:
  alice: "ssh-rsa AAAAB3... alice@example.com"
  bob: "ssh-rsa AAAAB3... bob@example.com"
```

### 2. Apply Terraform changes

```bash
cd tf
terraform plan  # Review changes - should show no VM recreation
terraform apply
```

**Note:** The VM _should not_ be recreated because only the additional users managed by Anisble have changed.

**Note:** To remove a user, this must be done manually. The users added by Ansible are all in the `ansible-added` group. The users added by Ansible, in addition to their home directory, will also have a file in the `/etc/sudoer.d/` directory which will need to be cleaned up.
