# Deployment Stack Role

Prepares mango-vm for the SKA SRCNet deployment stack.

## What This Role Does

- Installs **Docker Engine 27+** from Docker's own apt repository (`docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`) rather than Ubuntu's `docker.io` package, which can be older and may not include buildx. Also installs `make`, `git` and `gettext-base`.
- Verifies the installed Docker Engine meets the minimum required major version (`deployment_stack_docker_min_major`, default 27).
- Appends the cluster's local `*.test` hostnames to `/etc/hosts`, resolving to the load balancer on loopback (`127.0.0.1`).
- Raises inotify limits via `/etc/sysctl.d/99-inotify.conf` (`fs.inotify.max_user_instances=1024`, `fs.inotify.max_user_watches=524288`) and applies them with `sysctl --system`.
- Writes `/etc/docker/daemon.json` with a pinned `"mtu"` when the host NIC MTU is below 1500 (common on OpenStack), otherwise image pulls can hang.
- Logs the free space on the mount backing `/var/lib/docker`; the stack needs ~100 GB of images and volumes, so if the root disk is small, set `"data-root"` in `/etc/docker/daemon.json` to point at a larger volume.

Docker group membership is **not** managed here: users are created by the
`manage_users` role, so grant access via the per-user `groups` list in
`group_vars/all/users.yml` and run `manage_users.yml`:

```yaml
additional_users:
  - name: alice
    opkssh_claim_selector: alice@example.com
    static_ssh_key: ""
    groups:
      - docker
```

Note that `docker` group membership is effectively root-equivalent. Rootless
Docker is not an option because the cluster tooling relies on the standard
system socket.

## Outbound Access

The install pulls container images and source code from public registries:
Docker Hub, quay.io, ghcr.io, registry.k8s.io, gitlab.com, harbor.skao.int and
PyPI. The VM needs outbound HTTPS to these, or suitable proxy settings.

## Configuration

See [defaults/main.yml](defaults/main.yml) for the full list of variables
(package lists, sysctl values, hosts entries, MTU threshold).
