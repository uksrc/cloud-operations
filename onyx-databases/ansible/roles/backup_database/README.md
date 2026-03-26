# PostgreSQL Backup Role

## Database Restoration

The most important aspect of the Ansible role is that it creates backups of the Onyx databases.  Here's how to restore from those backups.

This can be done from the RAL Bastion host.  The DB VM IP needs to be known (which can be found from a `tofu output`
command run in the `onyx_database/tf` directory).

0. Consider [making a manual backup](#manually-trigger-a-backup) of the databases ahead of restoring from a backup.

1. Download a backup file from Swift or obtain the file from the local files on the DB server, as described [here](#accessing-backups).

2. Consider restoring the database into a new database to check its integrity:

    ```bash
    psql -h [DB_VM_IP] -U postgres -c 'CREATE DATABASE test_restore_database;'
    gunzip -c [BACKUP_FILE_STEM].sql.gz | psql -h [DB_VM_IP] -U postgres -d test_restore_database
    psql -h [DB_VM_IP] -U postgres -d test_restore_database \
      -c 'SELECT schemaname, relname AS table_name, n_live_tup AS row_count FROM pg_stat_user_tables ORDER BY schemaname, n_live_tup DESC;'
    ```

    ... and do any other checking that seems appropriate (e.g. with `\l`, `\c [database]`, `\dt *.*`, `SELECT * FROM [table]`).

    Delete the `test_restore_database` after finishing checks:

    ```base
    psql -h [DB_VM_IP] -U postgres -c 'DROP DATABASE test_restore_database;'
    ```

3. Once you're content that the backup is good, restore the database:

   ```bash
   sudo -u postgres dropdb [DATABASE_NAME]
   sudo -u postgres createdb [DATABASE_NAME]
   gunzip -c [BACKUP_FILE_STEM].sql.gz | psql -h [DB_VM_IP] -U postgres -d [DATABASE_NAME]
   ```

4. Verify database restoration:

   ```bash
   psql -h [DB_VM_IP] -U postgres
   ```

   ... and check the various databases (e.g. with `\l`, `\c [database]`, `\dt *.*`, `SELECT * FROM [table]`).

## Accessing Backups

### Local Backups on the DB VM

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

export OS_AUTH_TYPE="v3applicationcredential" OS_AUTH_URL=[]
export HISTCONTROL=ignorespace
 export OS_APPLICATION_CREDENTIAL_ID=[] OS_APPLICATION_CREDENTIAL_SECRET=[]
```

Then you can query the backups available in the object store:

```bash
swift list [CONTAINER_NAME]
```

... and download a backup:

```bash
swift download [CONTAINER_NAME] [BACKUP_NAME]
```

## Manually Trigger a Backup

The backup script (`/usr/local/bin/backup-postgres.sh`) performs the following:

- For each database in `backup_databases`:
  - Creates compressed SQL dump using `pg_dump`
  - Names file: `{hostname}_{database}_{timestamp}.sql.gz`
  - Uploads to Swift container
- Cleans up local backups older than `backup_retention_days`

This should be configured to run every 2 hours, but to trigger this manually:

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

## The Ansible Role

This Ansible role configures automated PostgreSQL database backups with upload to OpenStack Swift object storage.

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

### Configuration Variables

All variables are defined in `ansible/group_vars/all/backup.yml`.

#### Required Variables

- `backup_local_dir` - Local directory for backups
- `backup_databases` - Comma-separated list of databases to backup
- `swift_container_name` - Swift container name

#### OpenStack Authentication

These should be set via environment variables (in `ansible/.env`), they will be included in the Ansible variables from there:

- `OS_AUTH_URL` - OpenStack authentication URL
- `OS_APPLICATION_CREDENTIAL_ID` - Application credential ID
- `OS_APPLICATION_CREDENTIAL_SECRET` - Application credential secret

#### Optional Variables

- `backup_retention_days` - Days to keep local backups
- `backup_schedule` - Schedule frequency
- `backup_schedule_time` - Time to run backup
- `backup_schedule_enabled` - Enable/disable timer
- `backup_run_now` - Run immediate backup

### Usage

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

There are two types of backup created: `daily` and `frequent`.  The idea is that the
daily back ups are retained for longer.

The retention for the daily and frequent backups is set in the file [`ansible/group_vars/all/backup.yaml`](../../group_vars/all/backup.yml).

### Backup Locations

Local backups are stored on the database server in the directory `/var/backups/postgresql/`.

Also, backups are uploaded to OpenStack Swift object storage for off-site protection. The
container name is set in the file [`ansible/group_vars/all/backup.yml`](../../group_vars/all/backup.yml).
