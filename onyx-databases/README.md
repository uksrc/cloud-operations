# DB Server for Onyx Databases

This directory contains the configuration used to deploy databases and their host for the Onyx team development - e.g. metadata manager and software discovery service

There are more [docs in the Ansible directory](./ansible/README.md) on how to customise the database provision.

## Prereqs

- OpenTofu
- Ansible

## Usage

1. Set up S3 credentials:
   1. Find the project ID from `openstack project list`.
   2. List the credentials using `openstack credentials list` and matching the project ID.
   3. Set env vars `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY` to the `"access"` and `"secret"` values from the credential data, OR set these credentials in `~/.aws/credentials` like:

   ```toml
   [default]
   aws_access_key_id=[CREDENTIAL_ACCESS]
   aws_secret_access_key=[CREDENTIAL_SECRET]
   ```

2. Add `host_users.auto.tfvars` with users and SSH keys, based on the example, in the `tf` directory.
3. Add `.env` with database passwords, based on the example, in the `ansible` directory. **Important:** You need to set passwords for both preprod and prod environments for both CAOM and SDS databases.
4. Add a `users.yml` in the `ansible/group_vars/all` directory, see the example file in the same directory for hints.
5. Run OpenTofu:

```shell
cd tf
tofu plan
tofu apply
```

This will automatically deploy both preprod and prod environments for the CAOM and SDS databases.

## Verification

1. Obtain the metadata DB host IP from running, in the `tf` directory:

   ```shell
   tofu output
   ```

2. Connect to the DB host:

   ```shell
   # Connect to PostgreSQL
   ssh [USER]@[POSTGRES_VM_IP]
   ```

3. Check the databases. The deployment creates both preprod and prod databases:

   **CAOM Databases:**
   - `caom_preprod` - Preprod environment
   - `caom` - Production environment

   **SDS Databases:**
   - `software_discovery_preprod` - Preprod environment
   - `software_discovery` - Production environment

4. Connect with a database:

   ```shell
   # Connect to CAOM production database
   psql -U postgres -d caom -h localhost -W

   # Or connect to preprod
   psql -U postgres -d caom_preprod -h localhost -W

   # Check extensions
   \dx

   # Check schemas
   \dn

   # Check users
   \du
   ```

   Expected output for CAOM:
   - Extensions: citext, pg_sphere
   - Schemas: caom2, uws, tap_schema, tap_upload
   - Users: caom_admin, caom_tap_admin, caom_tap_user

5. Similar tests can be performed for the SDS databases (software_discovery and software_discovery_preprod).

Another test is to connect to the database from the bastion directly, without SSHing into the DB host first:

1. From bastion:

   ```shell
   psql -U postgres -h [POSTGRES_VM_IP]
   ```
