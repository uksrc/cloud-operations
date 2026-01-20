# SKA Metadata Manager PostgreSQL Ansible Playbook

This Ansible playbook configures a PostgreSQL database server for the SKA Metadata Manager according to the requirements documented at:
https://gitlab.com/ska-telescope/src/src-mm/ska-src-mm-metadata-manager

## What it does

1. **Updates the system** - Ensures all packages are up-to-date
2. **Installs PostgreSQL 15** - With required dependencies and the pg_sphere extension
3. **Configures the database cluster** - With proper encoding (UTF8) and collation (C) settings
4. **Creates database users**:
   - `cadmin` - Content admin for torkeep service
   - `tapadm` - TAP admin for argus service
   - `tapuser` - TAP user for argus service
5. **Creates the caomdb database** with required schemas:
   - `caom2` - For metadata content (owned by cadmin)
   - `uws` - For Universal Worker Service (owned by tapadm)
   - `tap_schema` - For TAP metadata (owned by tapadm)
   - `tap_upload` - For TAP uploads (owned by tapuser)
6. **Installs extensions**:
   - `citext` - Case-insensitive text
   - `pg_sphere` - Spatial query support

## Requirements

- Ubuntu 24.04 (Noble) target host
- Ansible 2.9+
- SSH access to the target host
- sudo privileges on the target host

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
   export CADMIN_PASSWORD="secure-password-here"
   export TAPADM_PASSWORD="secure-password-here"
   export TAPUSER_PASSWORD="secure-password-here"
   ```

3. The playbook will automatically load the `.env` file when you run it (configured in `ansible.cfg`)

#### Option 2: Export environment variables manually

```bash
export CADMIN_PASSWORD="secure-password-here"
export TAPADM_PASSWORD="secure-password-here"
export TAPUSER_PASSWORD="secure-password-here"
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

### Testing Locally with Vagrant

```bash
vagrant init ubuntu/noble64
vagrant up
ansible-playbook -i "192.168.56.10," -u vagrant postgres.yml
```

## Verification

After running the playbook, verify the setup:

```bash
# Connect to PostgreSQL
ssh user@postgres-vm
sudo -u postgres psql -d caomdb

# Check extensions
\dx

# Check schemas
\dn

# Check users
\du
```

Expected output:

- Extensions: citext, pg_sphere
- Schemas: caom2, uws, tap_schema, tap_upload
- Users: cadmin, tapadm, tapuser

## Security Notes

⚠️ **Important Security Considerations:**

1. **Change default passwords** - Use environment variables or vault
2. **Restrict network access** - Edit `pg_hba.conf` to limit connections
3. **Use SSL/TLS** - Configure PostgreSQL to require encrypted connections
4. **Firewall rules** - Limit PostgreSQL port (5432) access
5. **Regular backups** - Implement backup strategy
6. **Keep updated** - Apply security patches regularly

## Troubleshooting

### Connection refused

Check PostgreSQL is listening:

```bash
sudo netstat -plnt | grep 5432
```

### Permission denied

Ensure user has sudo privileges and proper SSH keys are configured.

## Integration with SKA Metadata Manager Services

After database setup, deploy the services:

1. **torkeep** (metadata repository): `images.opencadc.org/caom2/torkeep:2.0-BETA-02`
2. **argus** (TAP query service): `images.opencadc.org/caom2/argus:2.0-BETA-03`

Configure services to connect using the created database accounts.
