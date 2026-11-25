# Managing Additional Users

This role manages additional user accounts on the PostgreSQL VM. The primary user is created automatically during VM provisioning via cloud-init.

## Usage

### Initial Setup

1. Create your users configuration file:

   ```bash
   cd ansible/group_vars/all
   cp users.yml.example users.yml
   ```

2. Edit `users.yml` with your actual users (do not edit the `.example` file):

   ```yaml
   additional_users:
     - name: alice
       opkssh_claim_selector: <alice@example.com>
       static_ssh_key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... <alice@example.com>"
       groups:
        - docker
        - adm
       sudo: "alice ALL=(ALL) NOPASSWD:ALL"
   ```

   Each entry may also specify an optional `groups` list of extra groups the user is added to. For example, the deployment stack tooling calls Docker directly, so users who run it need `docker` group membership (effectively root-equivalent).
   By default no user is given sudo access. In order to provide a sudo access add a sudo key
   By default, `sshd` is configured so keys in user's `~/.ssh/authorized_keys`
   files do NOT permit login, unless user is in a group listed in
   `appliances_admin_user_groups` (default: `[adm]`).
   This is to prevent users provisioning their own keys instead of using OIDC.

3. Run the playbook:

   ```bash
   cd ansible
   ansible-playbook -i inventory manage_users.yml
   ```

**Note:** `users.yml` is gitignored to keep user details out of version control. Always update `users.yml`, not `users.yml.example`.

## What This Role Does

- Creates user accounts with home directories
- Creates any extra per-user groups that don't exist yet (from each user's optional `groups` list)
- Sets up SSH directories with correct permissions
- Adds SSH public keys to `~/.ssh/authorized_keys`
- Grants sudo access with NOPASSWD (if sudo key is defined else non sudo user will be created)
- Adds users to appropriate groups (defined in the group list) plus ansible-added
- **Automatically removes users** that were previously managed but are no longer in the list

**Note:** Once a group is assigned to a user it cannot be deleted automatically by simply removing it from the `user.yml` file. It needs to be done manually on the server same with is the case with sudoers list

## User Removal

Users created by this role are tagged with the `ansible-managed` group. When you remove a user from `additional_users` and run the playbook again, that user will be automatically removed from the system (including their home directory and sudoes file).

**Note:** The primary user is created by cloud-init during VM provisioning and is not managed by this role, so it is not at risk of removal. Only users listed in `additional_users` are managed (added or removed).

## Benefits

- Adding/removing users only requires running Ansible - **no VM recreation**
- Primary user creation is still fast (happens during initial VM boot)
- Consistent user management across multiple VMs
