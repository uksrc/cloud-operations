# ukSRC Deployment Stack

This deployment serves as a basis for the [**ukSRC DeploymentStack**](https://gitlab.com/ska-telescope/src/src-api/ska-src-api-deployment-stack/-/blob/main/INSTALL.md).

## Prereqs

- OpenTofu

## Usage

1. To store the TF state we use OpenStack's object store. The OpenStack object store has an AWS S3 interface, so we set up S3 credentials:
   1. Find the project ID from `openstack project list`.
   2. List the credentials using `openstack credentials list` and matching the project ID.
   3. Set env vars `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY` to the `"access"` and `"secret"` values from the credential data, OR set these credentials in `~/.aws/credentials` like:

   ```toml
   [default]
   aws_access_key_id=[CREDENTIAL_ACCESS]
   aws_secret_access_key=[CREDENTIAL_SECRET]
   ```

2. Add `host_users.auto.tfvars` with users and SSH keys, based on the example, in the `tf` directory.

3. Run OpenTofu:

   ```shell
   cd tf
   tofu init  # first time only
   tofu plan
   tofu apply
   ```
