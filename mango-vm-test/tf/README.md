# Mango VM Test Setup

This directory contains the configuration used to deploy the Mango test VM instance for cloud operations.

## VM Specifications

- **Name:** `mango-vm-test`
- **Flavor:** `l3.xsmall`
- **CPU:** 16 Cores
- **RAM:** 60 GB
- **Disk:** 400 GB
- **Default IP:** `192.168.64.104`

## Prereqs

- OpenTofu

## Usage

1. To store the TF state we use OpenStack's object store. The OpenStack object store has an AWS S3 interface, so we set up S3 credentials:
   1. Find the project ID by running on bastion `openstack project list`.
   2. List the credentials using `openstack credential list` and matching the project ID.
   3. Set env vars `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY` to the `"access"` and `"secret"` values from the credential data, OR set these credentials in `~/.aws/credentials` like:

   ```toml
   [default]
   aws_access_key_id=[CREDENTIAL_ACCESS]
   aws_secret_access_key=[CREDENTIAL_SECRET]
   ```

2. Add host_users.auto.tfvars with users and SSH keys, based on the example, in the tf directory.

3. Run OpenTofu - Before you run OT, define your clouds.yaml file (for example: OS_CLOUD=RAL) the easiest way to do this is just export it in the terminal using "export OS_CLOUD=RAL"

```shell
cd tf
tofu init

tofu plan

tofu apply
```

