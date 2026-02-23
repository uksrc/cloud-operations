# Metadata DB Server

This directory contains the configuration used to deploy the SKA Metadata DB server.

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
3. Add `.env` with database passwords, based on the example, in the `ansible` directory.
4. Run OpenTofu:

```shell
cd tf
tofu plan
tofu apply
```

## Verification

Obtain the metadata DB host IP from running, in the `tf` directory:

```shell
tofu output
```

After running the playbook, verify the setup:

```shell
# Connect to PostgreSQL
ssh [USER]@[POSTGRES_VM_IP]
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

The host and database are fairly secure, as they are only accessible from the UKSRC subnet and not expose to the public internet directly. However, there are few things that could be done to harden the host:

1. **Use SSL/TLS** - Configure PostgreSQL to require encrypted connections (this would require more from the client - all traffic should be inside the internal network, so risk is low)
2. **Firewall rules** - Limit PostgreSQL port (5432) access - this would be the 3rd level of security (pga_conf and Openstack security group in place, so risk while not having this is low)
3. **Regular backups** - Implement backup strategy (future ticket TBA)
