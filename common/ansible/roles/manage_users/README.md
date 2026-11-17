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
       opkssh_claim_selector: alice@example.com
       static_ssh_key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... alice@example.com"
       groups:
         - docker
     - name: bob
       opkssh_claim_selector: bob@example.com
       static_ssh_key: ""
   ```

   The optional `groups` list adds extra groups on top of the default admin
   groups (users, admin, wheel, ansible-added). Any extra groups that don't
   exist yet are created automatically, so users can be granted membership of
   groups whose packages aren't installed yet (e.g. `docker`).

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
- Grants sudo access with NOPASSWD
- Adds users to appropriate groups (users, admin, wheel, ansible-added, plus any per-user `groups`)
- **Automatically removes users** that were previously managed but are no longer in the list

## User Removal

Users created by this role are tagged with the `ansible-managed` group. When you remove a user from `additional_users` and run the playbook again, that user will be automatically removed from the system (including their home directory).

**Important:** The primary user is protected from removal. Ensure `primary_user` is set correctly in [manage_users.yml](../../../manage_users.yml).

## Benefits

- Adding/removing users only requires running Ansible - **no VM recreation**
- Primary user creation is still fast (happens during initial VM boot)
- Consistent user management across multiple VMs
