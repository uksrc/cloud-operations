# SKA Metadata Manager PostgreSQL Ansible Playbook

This Ansible playbook configures a PostgreSQL database server for the SKA Metadata Manager according to the requirements documented at:
<https://gitlab.com/ska-telescope/src/src-mm/ska-src-mm-metadata-manager>

## What it does

1. **Updates the system** - Ensures all packages are up-to-date
2. **Installs PostgreSQL 16** - With the pg_sphere extension
3. **Configures the database cluster** - With proper encoding (UTF8) and collation (C) settings
4. **Creates databases for both preprod and prod environments**:
   - **CAOM databases**: `caom_preprod` and `caom`
   - **SDS databases**: `software_discovery_preprod` and `software_discovery`
5. **Creates database users** (for each environment):
   - CAOM: `caom_admin`, `caom_tap_admin`, `caom_tap_user`
   - SDS: `sds_admin`, `sds_tap_admin`, `sds_tap_user`
6. **Creates required schemas**:
   - CAOM: `caom2`, `uws`, `tap_schema`, `tap_upload`
   - SDS: `sdm`, `uws`, `tap_schema`, `tap_upload`
7. **Installs extensions**:
   - `citext` - Case-insensitive text
   - `pg_sphere` - Spatial query support
   - `pgcrypto` - Cryptographic functions support (e.g. for encrypted columns)

## Requirements

- Ubuntu 24.04 (Noble) target host
- Ansible 2.9+

## Configuration

### Multi-Environment Setup

Both CAOM and SDS databases deploy preprod and prod environments automatically in a single playbook run by default. The configuration is managed via environment-specific variables.

You can optionally restrict a run to a **single environment** by passing `-e env=<name>` (valid values: `preprod`, `prod`). When omitted, all environments are deployed. Passing an invalid environment name fails fast before any database changes are made.

### CAOM Database

**Database Names:**

- Preprod: `caom_preprod`
- Production: `caom`

**Environment Variables:**

- Preprod: `CAOM_PREPROD_ADMIN_PASSWORD`, `CAOM_PREPROD_TAP_ADMIN_PASSWORD`, `CAOM_PREPROD_TAP_USER_PASSWORD`
- Production: `CAOM_ADMIN_PASSWORD`, `CAOM_TAP_ADMIN_PASSWORD`, `CAOM_TAP_USER_PASSWORD`

Configuration file: [group_vars/all/schema/caomdb.yml](group_vars/all/schema/caomdb.yml)

### SDS Database (Software Discovery Service)

**Database Names:**

- Preprod: `software_discovery_preprod`
- Production: `software_discovery`

**Environment Variables:**

- Preprod: `SDS_PREPROD_ADMIN_PASSWORD`, `SDS_PREPROD_TAP_ADMIN_PASSWORD`, `SDS_PREPROD_TAP_USER_PASSWORD`
- Production: `SDS_ADMIN_PASSWORD`, `SDS_TAP_ADMIN_PASSWORD`, `SDS_TAP_USER_PASSWORD`

Configuration file: [group_vars/all/schema/sdsdb.yml](group_vars/all/schema/sdsdb.yml)

### PostgreSQL Settings

Edit [group_vars/all/postgres.yml](group_vars/all/postgres.yml) to customize:

- `postgres_version`: PostgreSQL version (default: 16)
- `postgres_encoding`: Database encoding (default: UTF8)
- Other PostgreSQL-specific settings

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

### Setting Passwords (IMPORTANT!)

**DO NOT use default passwords in production!**

#### Option 1: Using .env file (Recommended for development)

1. Copy the example file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set your passwords:

   ```bash
   # PostgreSQL superuser
   export POSTGRES_PASSWORD="secure-password-here"

   # CAOM Database - Preprod
   export CAOM_PREPROD_ADMIN_PASSWORD="secure-password-here"
   export CAOM_PREPROD_TAP_ADMIN_PASSWORD="secure-password-here"
   export CAOM_PREPROD_TAP_USER_PASSWORD="secure-password-here"

   # CAOM Database - Production
   export CAOM_ADMIN_PASSWORD="secure-password-here"
   export CAOM_TAP_ADMIN_PASSWORD="secure-password-here"
   export CAOM_TAP_USER_PASSWORD="secure-password-here"

   # SDS Database - Preprod
   export SDS_PREPROD_ADMIN_PASSWORD="secure-password-here"
   export SDS_PREPROD_TAP_ADMIN_PASSWORD="secure-password-here"
   export SDS_PREPROD_TAP_USER_PASSWORD="secure-password-here"

   # SDS Database - Production
   export SDS_ADMIN_PASSWORD="secure-password-here"
   export SDS_TAP_ADMIN_PASSWORD="secure-password-here"
   export SDS_TAP_USER_PASSWORD="secure-password-here"
   ```

3. The playbook will automatically load the `.env` file when run via Terraform (configured in `ansible.cfg`)

#### Option 2: Export environment variables manually

```bash
export POSTGRES_PASSWORD='secure-password-here'

# CAOM Preprod
export CAOM_PREPROD_ADMIN_PASSWORD='secure-password-here'
export CAOM_PREPROD_TAP_ADMIN_PASSWORD='secure-password-here'
export CAOM_PREPROD_TAP_USER_PASSWORD='secure-password-here'

# CAOM Production
export CAOM_ADMIN_PASSWORD='secure-password-here'
export CAOM_TAP_ADMIN_PASSWORD='secure-password-here'
export CAOM_TAP_USER_PASSWORD='secure-password-here'

# SDS Preprod
export SDS_PREPROD_ADMIN_PASSWORD='secure-password-here'
export SDS_PREPROD_TAP_ADMIN_PASSWORD='secure-password-here'
export SDS_PREPROD_TAP_USER_PASSWORD='secure-password-here'

# SDS Production
export SDS_ADMIN_PASSWORD='secure-password-here'
export SDS_TAP_ADMIN_PASSWORD='secure-password-here'
export SDS_TAP_USER_PASSWORD='secure-password-here'
```

#### Option 3: Use Ansible Vault (Recommended for production)

```bash
ansible-vault create group_vars/all/vault.yml
```

## Usage

### From Terraform/OpenTofu (Automated)

The Terraform configuration will automatically run the playbooks after creating the VM. Both preprod and prod environments for CAOM and SDS databases are deployed automatically.

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

   # Deploy ALL environments (both preprod and prod) by default
   ansible-playbook -i inventory setup_mm_db_schema.yml
   ansible-playbook -i inventory setup_sds_db_schema.yml

   # Deploy a SINGLE environment only
   ansible-playbook -i inventory setup_mm_db_schema.yml -e env=preprod
   ansible-playbook -i inventory setup_mm_db_schema.yml -e env=prod
   ansible-playbook -i inventory setup_sds_db_schema.yml -e env=preprod
   ansible-playbook -i inventory setup_sds_db_schema.yml -e env=prod

   # Invalid environment names fail fast, e.g.:
   ansible-playbook -i inventory setup_mm_db_schema.yml -e env=bogus   # aborts: invalid environment
   ```

By default, each playbook deploys both preprod and prod environments. Pass `-e env=<name>` to deploy only that environment (e.g. `-e env=preprod`).
