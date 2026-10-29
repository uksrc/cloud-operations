# VM Ansible Playbook

This Ansible playbook configures a server.

## What it does

1. **Updates the system** - Ensures all packages are up-to-date
2. **Adds users**
3. **Installs deployment stack prerequisites** - Docker Engine 27+ from Docker's apt repo, local `*.test` hostnames, inotify limits and Docker daemon settings for the SKA SRCNet deployment stack
4. **Adds OPKSSH**

## Requirements

- Ubuntu 24.04 (Noble) target host (provided by TF code)
- Ansible 2.9+

### User Management

Additional system users (beyond the primary user created via Terraform) are managed through Ansible.

**Setup:**

1. Create your users configuration file:

   ```bash
   cd group_vars/all
   cp users.yml.example users.yml
   ```

2. Edit `users.yml` (not the `.example` file) with your actual users and SSH keys:

   ```yaml
   additional_users:
     - name: alice
       opkssh_claim_selector: alice@example.com
       static_ssh_key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... alice@example.com"
       groups:
         - docker
     - name: bob
       opkssh_claim_selector: bob@example.com
       static_ssh_key: ""
   ```

   The optional `groups` list adds extra groups on top of the default admin
   groups. Users who run the deployment stack tooling need `docker` group
   membership (effectively root-equivalent).

3. Deploy users:

   ```bash
   ansible-playbook -i inventory manage_users.yml
   ```

**Note:** `users.yml` is gitignored to keep SSH keys out of version control. See [roles/manage_users/README.md](../../../common/ansible/roles/manage_users/README.md) for more details.

### Deployment Stack Prerequisites

The `deployment_stack.yml` playbook prepares the VM for the SKA SRCNet deployment stack:

- **Docker Engine 27+** from Docker's own apt repository (`docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`), plus `make`, `git` and `gettext-base`. Ubuntu's `docker.io` package is deliberately not used: the stack requires version 27 or newer and the buildx plugin.
- **Docker access** - the stack's tooling calls Docker directly and mounts the Docker socket into its management container, so users who run it need to be in the `docker` group (effectively root-equivalent). Grant this via the per-user `groups` list in `users.yml` (see above) and run `manage_users.yml`; rootless Docker is not supported because the cluster tooling relies on the standard system socket.
- **Hosts file entries** - appends the cluster's local `*.test` hostnames (headlamp.test, console.test, vault.test, etc.) to `/etc/hosts`, resolving to the load balancer on loopback (`127.0.0.1`).
- **Kernel settings** - raises inotify limits (`fs.inotify.max_user_instances=1024`, `fs.inotify.max_user_watches=524288`) via `/etc/sysctl.d/99-inotify.conf`, as the cluster and dev tooling watch many files.
- **Docker daemon settings** - if the VM's network MTU is below 1500 (common on OpenStack), writes `/etc/docker/daemon.json` with a matching `"mtu"` so image pulls don't hang. The stack needs ~100 GB of Docker images and volumes; if `/var/lib/docker` sits on a small root disk, set `"data-root"` in `/etc/docker/daemon.json` to point at a larger volume (the role logs the available space).

The install pulls container images and source code from public registries (Docker Hub, quay.io, ghcr.io, registry.k8s.io, gitlab.com, harbor.skao.int and PyPI), so the VM needs outbound HTTPS to these, or suitable proxy settings.

Run it manually with:

```bash
ansible-playbook -i inventory deployment_stack.yml
```

## Usage

### From Terraform/OpenTofu (Automated)

The Terraform configuration will automatically run the playbooks after creating the VM.

### Manual Execution

If you need to run the playbooks manually:

1. Create an inventory file with your host:

   ```ini
   [postgres]
   your-host-ip ansible_user=your-username
   ```

2. Run the playbooks:

   ```bash
   cd ansible


   ```
