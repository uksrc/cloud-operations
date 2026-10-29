# VM Ansible Playbook

This Ansible playbook configures a server.

## What it does

1. **Updates the system** - Ensures all packages are up-to-date
2. **Adds users**
3. **Adds OPKSSH**

## Requirements

- Ubuntu 24.04 (Noble) target host (provided by TF code)
- Ansible 2.9+

### User Management

Additional system users (beyond the primary user created via Terraform) are managed through Ansible.

**Setup:**

1. Create your users configuration file:

   ```bash
   cd group_vars/all
   cp users.yml.example users.yml
   ```

2. Edit `users.yml` (not the `.example` file) with your actual users and SSH keys:

   ```yaml
   additional_users:
     alice: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... alice@example.com"
     bob: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ... bob@example.com"
   ```

3. Deploy users:

   ```bash
   ansible-playbook -i inventory manage_users.yml
   ```

**Note:** `users.yml` is gitignored to keep SSH keys out of version control. See [roles/manage_users/README.md](roles/manage_users/README.md) for more details.

## Usage

### From Terraform/OpenTofu (Automated)

The Terraform configuration will automatically run the playbooks after creating the VM.

### Manual Execution

If you need to run the playbooks manually:

1. Create an inventory file with your host:

   ```ini
   [postgres]
   your-host-ip ansible_user=your-username
   ```

2. Run the playbooks:

   ```bash
   cd ansible

    
   ```
