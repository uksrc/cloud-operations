# add_opkssh

Ansible role to install and configure [opkssh](https://github.com/openpubkey/opkssh)
(OpenPubkey SSH), so users can SSH in with short-lived OpenID Connect
certificates instead of static SSH keys.

Supports Ubuntu and Rocky Linux. On SELinux-enabled systems (Rocky) the
upstream `opkssh.te` policy module is compiled and installed; no AppArmor
configuration is needed on Ubuntu.

## Role variables

See [defaults/main.yml](defaults/main.yml) for the full list. The ones you
will most likely set per-deployment:

| Variable | Default | Description |
|----------|---------|-------------|
| `opkssh_providers` | SKA IAM (production client ID) | OIDC providers, keyed by name, each with `issuer_uri`, `client_id`, `expires` |
| `opkssh_auth_id` | `[]` | List of `{name: <linux user>, opkssh_claim_selector: <email|sub|group>}` authorising users |
| `opkssh_disable_authorized_keys` | `true` | Disable `~/.ssh/authorized_keys` globally |
| `opkssh_enable_authorized_keys_groups` | `[adm]` | Groups whose `~/.ssh/authorized_keys` still works |
| `opkssh_install_version` | `v0.14.0` | opkssh release to install |
| `opkssh_selinux_enable_*` | `false` | SELinux booleans (home policy / proxies) |

## Example playbook

```yaml
- name: Install and configure opkssh
  hosts: all
  become: true
  vars:
    opkssh_auth_id:
      - name: jane
        opkssh_claim_selector: jane@example.com
  roles:
    - add_opkssh
```

The users listed in `opkssh_auth_id` must already exist on the host (e.g.
via the `manage_users` role).

## Handlers

- `Restart OpenSSH server` — restarts `sshd` (Rocky) or `ssh` (Ubuntu) when
  the sshd configuration changes.
