# PostgreSQL Backup Role

This Ansible role configures automated PostgreSQL database backups with upload to OpenStack Swift object storage.

## What the Ansible Role does

1. Installs required packages:
   - `python3-swiftclient` - OpenStack Swift CLI
   - `python3-keystoneclient` - OpenStack authentication
   - `postgresql-client` - Database backup tools

2. Creates backup infrastructure:
   - Local backup directory (`/var/backups/postgresql`)
   - Backup script (`/usr/local/bin/backup-postgres.sh`)
   - OpenStack credentials file (`/etc/postgresql/.openstack-backup.rc`)

3. Configures systemd:
   - Daily service (`postgres-backup-daily.service`)
   - .. and timer (`postgres-backup-daily.timer`)
   - Frequent service (`postgres-backup-frequent.service`)
   - ... and timer (`postgres-backup-frequent.timer`)
   - Enables and starts both timers

4. Optionally runs an immediate backup (if `backup_run_now: true`)

## Configuration Variables

All variables are defined in `ansible/group_vars/all/backup.yml`.

### Required Variables

- `backup_local_dir` - Local directory for backups
- `backup_databases` - Comma-separated list of databases to backup
- `swift_container_name` - Swift container name

### OpenStack Authentication

These should be set via environment variables (in `ansible/.env`), they will be included in the Ansible variables from there:

- `OS_AUTH_URL` - OpenStack authentication URL
- `OS_APPLICATION_CREDENTIAL_ID` - Application credential ID
- `OS_APPLICATION_CREDENTIAL_SECRET` - Application credential secret

### Optional Variables

- `backup_retention_days` - Days to keep local backups
- `backup_schedule` - Schedule frequency
- `backup_schedule_time` - Time to run backup
- `backup_schedule_enabled` - Enable/disable timer
- `backup_run_now` - Run immediate backup

## Backup Script

The backup script (`/usr/local/bin/backup-postgres.sh`) performs the following:

- For each database in `backup_databases`:
  - Creates compressed SQL dump using `pg_dump`
  - Names file: `{hostname}_{database}_{timestamp}.sql.gz`
  - Uploads to Swift container
- Cleans up local backups older than `backup_retention_days`

## Usage

### Deploy Backup System

Run via Terraform:

```bash
cd tf
tofu apply
```

Or run Ansible playbook directly:

```bash
cd ansible
ansible-playbook -i [HOST_IP], -u [USER] setup_backups.yml
```

### Manual Backup

```bash
# Trigger daily backup
sudo systemctl start postgres-backup-daily.service

# Trigger frequent backup
sudo systemctl start postgres-backup-frequent.service
```

... or directly run the script:

```bash
# Run daily backup manually
sudo -u postgres bash -c 'cd /tmp && /usr/local/bin/backup-postgres-daily.sh'

# Run frequent backup manually
sudo -u postgres bash -c 'cd /tmp && /usr/local/bin/backup-postgres-frequent.sh'
```

### Check Timer Status

```bash
# Check both timers
systemctl status postgres-backup-daily.timer
systemctl status postgres-backup-frequent.timer

# List all backup timers with schedule info
systemctl list-timers postgres-backup-*
```

### View Logs

```bash
# View daily backup logs
journalctl -u postgres-backup-daily.service -n 50

# View frequent backup logs
journalctl -u postgres-backup-frequent.service -n 50

# View all backup logs
journalctl -u postgres-backup-*.service -n 100
```

## Backup Format

Backups are stored as compressed SQL dumps with a type prefix:

- Filename format: `{type}_{hostname}_{database}_{timestamp}.sql.gz`
- Example daily: `daily_postgres-vm_caom_20260318_020000.sql.gz`
- Example frequent: `frequent_postgres-vm_caom_20260318_140000.sql.gz`
- Compression: gzip
- Content: Full PostgreSQL database dump created with `pg_dump`

### Backup Types

- `daily` - Daily backups at 00:00, retained for 7 days (both local and Swift)
- `frequent` - Backups every 2 hours, retained for 1 day (both local and Swift)

## Backup Locations

### Local Storage

Local backups are stored on the database server:

- **Directory**: `/var/backups/postgresql/`
- **Permissions**: `0750`, owned by `postgres:postgres`
- **Retention**: Files older than `backup_retention_days` (default: 7 days) are automatically deleted
- **Purpose**: Recent backups for quick local recovery

### Remote Storage (OpenStack Swift)

Backups are uploaded to OpenStack Swift object storage for off-site protection:

- **Container**: `uksrc-backups` (default, configurable via `swift_container_name`)
- **Object naming**: Same as local filename (e.g., `daily_postgres-vm_caomdb_20260318_020000.sql.gz`)
- **Retention**: Automatic cleanup based on backup type:
  - Daily backups: 7 days
  - Frequent backups: 1 day
- **Purpose**: Long-term retention and disaster recovery

## Accessing Backups

### Local Backups

On the database server:

```bash
# As root or with sudo
ls -lh /var/backups/postgresql/

# As postgres user
# List daily backups
ls -lh /var/backups/postgresql/daily_*.sql.gz

# List frequent backups
ls -lh /var/backups/postgresql/frequent_*.sql.gz

# Find specific database backups (daily only)
ls -lh /var/backups/postgresql/daily_*_caom_*.sql.gz

# Show backups from last 7 days
find /var/backups/postgresql/ -name "*.sql.gz" -mtime -7 -ls
```

### Swift Backups

From the database server or any system with Swift client access, you can use the backups stored in the OpenStack object store ("Swift").

Firstly, make sure the client can authenticate:

```bash
# Authenticate and list all backups in the container
# On the database VM
sudo -u postgres bash
source /etc/postgresql/.openstack-backup.rc

# Or on any RAL host with the swift cli tool installed
export HISTCONTROL=ignorespace
 export OS_AUTH_URL=[] OS_APPLICATION_CREDENTIAL_ID=[] OS_APPLICATION_CREDENTIAL_SECRET=[] OS_AUTH_TYPE="v3applicationcredential"
```

#### List Swift Backups

Then you can query the backups available in the object store:

```bash
# List all containers
swift list

# List contents of the backup container
swift list [CONTAINER_NAME]

# List backups with details (size, date)
swift list [CONTAINER_NAME] --long

# List daily backups only
swift list [CONTAINER_NAME] --prefix daily_

# List frequent backups only
swift list [CONTAINER_NAME] --prefix frequent_

# List daily backups for specific database (e.g. `caom`)
swift list [CONTAINER_NAME] --prefix daily_postgres-vm_[DATABASE_NAME]_

# List frequent backups from a specific date (e.g. `caom` for 18th March 2026)
swift list [CONTAINER_NAME] --prefix frequent_postgres-vm_[DATABASE_NAME]_20260318
```

#### Download Backups from Swift

After setting up the authentication

```bash
# Download a specific daily backup
swift download [CONTAINER_NAME] daily_postgres-vm_[DATABASE_NAME]_20260318_000000.sql.gz -o /tmp/backup.sql.gz

# Download a specific frequent backup
swift download [CONTAINER_NAME] frequent_postgres-vm_[DATABASE_NAME]_20260318_140000.sql.gz -o /tmp/backup.sql.gz

# Download all daily backups for a database
swift download [CONTAINER_NAME] --prefix daily_postgres-vm_[DATABASE_NAME]_

# Download all frequent backups from today
swift download [CONTAINER_NAME] --prefix frequent_postgres-vm_[DATABASE_NAME]_$(date +%Y%m%d)

# Download entire container
swift download [CONTAINER_NAME]
```

## Database Restoration

1. Download a backup file from Swift or obtain the file from the local files on the DB server, as described above.

2. Restore the database:

   ```bash
   # Option A: Restore to existing database (overwrites data) - using daily backup
   gunzip -c /var/backups/postgresql/daily_postgres-vm_[DATABASE_NAME]_20260318_000000.sql.gz | \
       sudo -u postgres psql [DATABASE_NAME]

   # Option B: Drop and recreate database (clean restore) - using daily backup
   sudo -u postgres dropdb caomdb
   sudo -u postgres createdb caomdb -O caomdb_owner
   gunzip -c /var/backups/postgresql/daily_postgres-vm_[DATABASE_NAME]__20260318_000000.sql.gz | \
       sudo -u postgres psql caomdb

   # Option C: Restore from recent frequent backup (if daily is too old)
   gunzip -c /var/backups/postgresql/frequent_postgres-vm_[DATABASE_NAME]__20260318_140000.sql.gz | \
       sudo -u postgres psql caomdb
   ```

3. Verify database restoration:

   From RAL Bastion:

   ```bash
   psql -h 192.168.66.106 -U postgres
   ```

   ... and check the various databases (e.g. with `\l`, `\c [database]`, `\dt`, `SELECT * FROM [table]`).
