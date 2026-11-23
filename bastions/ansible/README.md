# VM Ansible Playbook

This Ansible playbook configures a server.

## What it does

1. **Adds users**
2. **Adds OPKSSH**

## Requirements

- Ubuntu 24.04 (Noble) target host (provided by TF code)
- Ansible 2.9+

### User Management

Additional system users (beyond the primary user and service accounts) are managed through Ansible.

**Setup:**

1. Create your users configuration file:

   ```bash
   cd group_vars/all
   cp users.yml.example users.yml
   ```

2. Edit `users.yml` (not the `.example` file) with your actual users and SSH keys

   ```yaml
   additional_users:
     - name: alice
       opkssh_claim_selector: alice@example.com
       static_ssh_key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... alice@example.com"
       groups:
         - docker
     - name: bob
       opkssh_claim_selector: bob@example.com
       static_ssh_key: ""
   ```

   The optional `groups` list adds extra groups on top of the default admin
   groups. Users who run the deployment stack tooling need `docker` group
   membership (effectively root-equivalent).

3. Deploy users:

   ```bash
   ansible-playbook -i inventory manage_users.yml
   ```

**Note:** `users.yml` is gitignored to keep SSH keys out of version control. See [roles/manage_users/README.md](../../../common/ansible/roles/manage_users/README.md) for more details.

### Setup OPKSSH

OPKSSH can be setup by simply running the opkssh playbook right after manage_user.yml

**Setup:**

1. Setup opkssh:

   ```bash
   ansible-playbook -i inventory add_opkssh.yml
   ```
