# SKA Metadata Manager PostgreSQL Ansible Playbook

This Ansible playbook configures a PostgreSQL database server for the SKA Metadata Manager according to the requirements documented at:
https://gitlab.com/ska-telescope/src/src-mm/ska-src-mm-metadata-manager

## What it does

1. **Updates the system** - Ensures all packages are up-to-date
2. **Installs PostgreSQL 16** - With the pg_sphere extension
3. **Configures the database cluster** - With proper encoding (UTF8) and collation (C) settings
4. **Creates database users**:
   - `caom_admin` - CAOM content admin
   - `caom_tap_admin` - CAOM TAP admin
   - `caom_tap_user` - CAOM TAP user
5. **Creates the caomdb database** with required schemas:
   - `caom2` - For metadata content (owned by caom_admin)
   - `uws` - For Universal Worker Service (owned by caom_tap_admin)
   - `tap_schema` - For TAP metadata (owned by caom_tap_admin)
   - `tap_upload` - For TAP uploads (owned by caom_tap_user)
6. **Installs extensions**:
   - `citext` - Case-insensitive text
   - `pg_sphere` - Spatial query support

## Requirements

- Ubuntu 24.04 (Noble) target host
- Ansible 2.9+

## Configuration

Edit [group_vars/all/variables.yml](group_vars/all/variables.yml) to customize:

- `postgres_version`: PostgreSQL version (default: 16)
- `database_name`: Database name (default: caomdb)
- `db_users`: User accounts and passwords

### Setting Passwords (IMPORTANT!)

**DO NOT use default passwords in production!**

#### Option 1: Using .env file (Recommended for development)

1. Copy the example file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set your passwords:

   ```bash
   export CAOM_ADMIN_PASSWORD="secure-password-here"
   export CAOM_TAP_ADMIN_PASSWORD="secure-password-here"
   export CAOM_TAP_USER_PASSWORD="secure-password-here"
   ```

3. The playbook will automatically load the `.env` file when you run it (configured in `ansible.cfg`)

#### Option 2: Export environment variables manually

```bash
export CAOM_ADMIN_PASSWORD="secure-password-here"
export CAOM_TAP_ADMIN_PASSWORD="secure-password-here"
export CAOM_TAP_USER_PASSWORD="secure-password-here"
```

#### Option 3: Use Ansible Vault (Recommended for production)

```bash
ansible-vault create group_vars/all/vault.yml
```

## Usage

### From Terraform/OpenTofu (Automated)

The Terraform configuration will automatically run this playbook after creating the VM.

### Manual Execution

1. Create an inventory file with your host:

   ```ini
   [postgres]
   your-host-ip ansible_user=your-username
   ```

2. Run the playbook:

   ```bash
   cd ansible
   ansible-playbook -i inventory postgres.yml
   ```
