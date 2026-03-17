# PostgreSQL Backup Role

This Ansible role configures automated PostgreSQL database backups with upload to OpenStack Swift object storage.

## Features

- **Automated daily backups** via systemd timer
- **OpenStack Swift integration** for off-site backup storage
- **Local backup retention** with configurable retention period
- **Multiple database support** - backup multiple databases in one run
- **Systemd integration** for reliable scheduling and logging
- **On-demand backups** - can be triggered manually or during provisioning

## What It Does

1. Installs required packages:
   - `python3-swiftclient` - OpenStack Swift CLI
   - `python3-keystoneclient` - OpenStack authentication
   - `postgresql-client` - Database backup tools

2. Creates backup infrastructure:
   - Local backup directory (`/var/backups/postgresql`)
   - Backup script (`/usr/local/bin/backup-postgres.sh`)
   - OpenStack credentials file (`/etc/postgresql/.openstack-backup.rc`)

3. Configures systemd:
   - Service unit (`postgres-backup.service`)
   - Timer unit (`postgres-backup.timer`)
   - Enables and starts the timer

4. Optionally runs an immediate backup (if `backup_run_now: true`)

## Configuration Variables

All variables are defined in `ansible/group_vars/all/backup.yml`:

### Required Variables

- `backup_local_dir` - Local directory for backups (default: `/var/backups/postgresql`)
- `backup_databases` - Comma-separated list of databases to backup (default: `postgres,caomdb,sdsdb`)
- `swift_container_name` - Swift container name (default: `postgres-backups`)

### OpenStack Authentication

These should be set via environment variables (in `ansible/.env`):

- `OS_AUTH_URL` - OpenStack authentication URL
- `OS_PROJECT_NAME` - Project/tenant name
- `OS_USERNAME` - Username
- `OS_PASSWORD` - Password
- `OS_USER_DOMAIN_NAME` - User domain (default: `Default`)
- `OS_PROJECT_DOMAIN_NAME` - Project domain (default: `Default`)
- `OS_REGION_NAME` - Region (default: `RegionOne`)

### Optional Variables

- `backup_retention_days` - Days to keep local backups (default: `7`)
- `backup_schedule` - Schedule frequency (default: `daily`)
- `backup_schedule_time` - Time to run backup (default: `02:00`)
- `backup_schedule_enabled` - Enable/disable timer (default: `true`)
- `backup_run_now` - Run immediate backup (default: `false`)

## Backup Script

The backup script (`/usr/local/bin/backup-postgres.sh`) performs the following:

1. For each database in `backup_databases`:
   - Creates compressed SQL dump using `pg_dump`
   - Names file: `{hostname}_{database}_{timestamp}.sql.gz`
   - Uploads to Swift container (if configured)

2. Cleans up local backups older than `backup_retention_days`

3. Logs all operations with timestamps

4. Returns exit code 0 on success, 1 on failure

## Systemd Integration

### Service Unit

The service unit (`postgres-backup.service`):

- Runs as `postgres` user
- Executes backup script
- Logs to systemd journal
- One-shot execution type

### Timer Unit

The timer unit (`postgres-backup.timer`):

- Scheduled via `OnCalendar` directive
- Persistent scheduling (catches up if system was down)
- Installed in `timers.target`

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
sudo -u postgres /usr/local/bin/backup-postgres.sh
```

### Check Timer Status

```bash
systemctl status postgres-backup.timer
systemctl list-timers postgres-backup.timer
```

### View Logs

```bash
journalctl -u postgres-backup.service -n 50
```

### Trigger Backup via Systemd

```bash
sudo systemctl start postgres-backup.service
```

## Backup Format

Backups are stored as compressed SQL dumps:

- Filename format: `{hostname}_{database}_{timestamp}.sql.gz`
- Example: `postgres-vm_caomdb_20260223_143022.sql.gz`
- Compression: gzip

## Swift Storage

Backups are uploaded to OpenStack Swift:

- Container is auto-created if it doesn't exist
- Object name matches local filename
- Original file kept locally subject to retention policy

## Restoration

To restore from a backup:

1. Download from Swift:

    ```bash
    source /etc/postgresql/.openstack-backup.rc
    swift download postgres-backups [BACKUP_FILE] -o /tmp/backup.sql.gz
    ```

2. Restore database:

    ```bash
    # Optional: drop existing database
    sudo -u postgres dropdb [DATABASE_NAME]
    sudo -u postgres createdb [DATABASE_NAME]

    # Restore
    gunzip -c /tmp/backup.sql.gz | sudo -u postgres psql [DATABASE_NAME]
    ```

## Security Considerations

- OpenStack credentials stored in `/etc/postgresql/.openstack-backup.rc` (mode 0600, owner postgres)
- Backup script runs as postgres user (principle of least privilege)
- Systemd service has security hardening (`PrivateTmp`, `NoNewPrivileges`)
- Local backups in `/var/backups/postgresql` (mode 0750, owner postgres)

## Troubleshooting

### Check if timer is running

```bash
systemctl is-active postgres-backup.timer
systemctl list-timers
```

### Run backup manually to test

```bash
sudo -u postgres /usr/local/bin/backup-postgres.sh
```

### Check for errors

```bash
journalctl -u postgres-backup.service -xe
```

### Verify Swift connectivity

```bash
sudo -u postgres bash
source /etc/postgresql/.openstack-backup.rc
swift list
```

### Test database access

```bash
sudo -u postgres pg_dump postgres > /dev/null
```

## Dependencies

- PostgreSQL must be installed and running
- OpenStack credentials must be configured
- Swift container is auto-created by the script
