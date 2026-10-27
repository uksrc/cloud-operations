# opkssh standalone playbook

Installs and configures [opkssh](https://github.com/openpubkey/opkssh)
(OpenPubkey SSH) on a host, so users can SSH in with short-lived OpenID
Connect certificates instead of static SSH keys. It is equivalent to the
`opkssh` role in this repository but has no dependency on appliance
variables, so it can be run against any freshly provisioned host.

## What it does

- **Checks:** asserts that `opkssh_providers` and
  `opkssh_auth_id` have the required keys.
- **Install:** creates the `opksshuser` user/group and downloads the opkssh
  binary to `/usr/local/bin`.
- **SELinux (Rocky and other enforcing systems):** compiles and installs the
  upstream `opkssh.te` policy module (trying the `sshd_session_t` variant
  first, falling back to `sshd_t`, like the upstream install script) and sets
  its booleans from the `opkssh_selinux_*` variables. Skipped entirely when
  SELinux is disabled (e.g. Ubuntu). No AppArmor configuration is needed:
  Ubuntu's default policy does not confine sshd or `AuthorizedKeysCommand`.
- **Configure:** refuses to run if another sshd config file already sets
  `AuthorizedKeysCommand`, then writes
  `/etc/ssh/sshd_config.d/60-opk-ssh.conf`, `/etc/opk/providers` and
  `/etc/opk/auth_id`. sshd is restarted via a handler when its config
  changes.

## Files

| File | Purpose |
|------|---------|
| `opkssh-standalone.yml` | The playbook |
| `opkssh-standalone-vars.yml` | Default variables (binary version, SKA IAM provider, etc.) |
| `users.yml.example` | Template for the list of users to authorise |
| `users.yml` | Your copy of the above (gitignored, not committed) |

## Supported platforms

Tested targets are **Ubuntu** and **Rocky Linux**. OS-dependent values are
derived from gathered facts (so don't disable fact gathering), and can be
overridden with `-e` if needed:

| Variable | Ubuntu | Rocky |
|----------|--------|-------|
| `opkssh_sshd_service` | `ssh` | `sshd` |
| `opkssh_nologin_shell` | `/usr/sbin/nologin` | `/sbin/nologin` |
| `opkssh_install_arch` | `amd64`/`arm64` from host architecture | same |

## Setup

1. Copy the example users file and edit it:

   ```
   cp users.yml.example users.yml
   ```

   Each entry maps a Linux user on the host to an identity claim from the
   OIDC provider (usually an email address):

   ```yaml
   opkssh_auth_id:
     - name: jane
       opkssh_claim_selector: jane@example.com
   ```

2. Review `opkssh-standalone-vars.yml`. The SKA IAM provider is configured
   with the production client ID; the staging ID is in a comment. Any
   `opkssh_*` variable can also be overridden with `-e` on the command line.

## Running it

`target` defaults to the `opkssh` inventory group; override it (e.g. with
`all` when using an ad-hoc inventory) and pass the host inline:

```
ansible-playbook -i 'host1.example.com,' opkssh-standalone.yml -e target=all -u clouduser
```

## Using it from OpenTofu/Terraform provisioners

This follows the same pattern as the `onyx-databases` deployment: a
`null_resource` with a `local-exec` provisioner runs the playbook, and
`triggers` re-run it when the playbook or its variables change. Add
something like this to your `tf/` configuration:

```hcl
locals {
  opkssh_command = <<-EOT
    cd ${path.module}/../ansible/opkssh
    ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
      -i '${openstack_compute_instance_v2.my_vm.access_ip_v4},' \
      -u ${var.primary_user} \
      opkssh-standalone.yml -e target=all
  EOT
}

resource "null_resource" "opkssh_provisioner" {
  # Run after the host exists and users have been created
  depends_on = [null_resource.manage_users_provisioner]

  triggers = {
    host_instance_id         = openstack_compute_instance_v2.my_vm.id
    playbook_hash            = filemd5("${path.module}/../ansible/opkssh/opkssh-standalone.yml")
    vars_hash                = filemd5("${path.module}/../ansible/opkssh/opkssh-standalone-vars.yml")
    users_hash               = try(filemd5("${path.module}/../ansible/opkssh/users.yml"), "")
    provisioner_command_hash = md5(local.opkssh_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.opkssh_command
  }
}
```

Notes:

- The users listed in `users.yml` must already exist on the host (e.g. via
  the `manage_users` playbook), hence the `depends_on` above.
- `try(filemd5(...), "")` on `users.yml` means `tofu plan` still works
  before you have created it, but the provisioner will fail at apply time
  if the file is missing.
