# xrootd installation

Server creation and configuration is carried out in two steps:

- Virtual machine deployment with Opentofu
- Server setup with ansible

## Prereqs

### Python

Create a python environment with openstack and ansible tools e.g. in the code top level:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Openstack

Openstack application credentials for your project and EC2 credentials:

```
export OS_CLOUD=<cloud name, default 'openstack'>
export AWS_ACCESS_KEY_ID=<key id>
export AWS_SECRET_ACCESS_KEY=<access key>
```

Create an S3 bucket to store the Opentofu state, one bucket per server.

Create a new ssh key for the server default user and upload to openstack. This key-pair will be used during deployment.

### Ansible

The ansible vault password. Pass to ansible-playbook either with the --vault-password-file option or ANSIBLE_VAULT_PASSWORD_FILE env var.

### Storage

We are using openstack manila shares for XRootD storage. Create a share and add a readwrite access rule

openstack share create CephFS <size in GB> --name <share name> --share-type ceph01_cephfs
openstack share access create <share name> cephx <rule name>

The share details should be ansible vault encrypted in the host_vars file.

### VM Base Image

Rocky base images can be downloaded from [Rocky Linux ISOs and Images](https://wiki.rockylinux.org/rocky/image/)

Upload to the openstack project

```
openstack image create --disk-format qcow2 \
    --property hw_machine_type=q35 \
    --property hw_architecture=x86_64 \
    --property hw_vif_multiqueue_enabled=true \
    --property hw_firmware_type=uefi \
    --property os_type=linux \
    --property hw_disk_bus=virtio \
    --file ./<base image name>.qcow2 <base image name>-<date>-UEFI
```

## VM Creation

```
cd xrootd/tf
```

Create or edit the tfvars file for your server and set the necessary variables. See the xrootd-server.tfvars.example file. The .gitignore file is set to ignore .tfvars files so they are not checked in
This file is

You are now ready to create the machine:

```
tofu init
tofu init -var-file <server>.tfvars
tofu plan -var-file cam-prod.tfvars
tofu apply -var-file cam-prod.tfvars
```

The output includes the local IP of the new instance. Add that to the ansible inventory.

Test logging into the machine with the default user and the new ssh key.

## Ansible

```
cd ../ansible
```

We use some [dev-sec](https://dev-sec.io/) ansible roles for [OS and SSH hardening](https://github.com/dev-sec/ansible-collection-hardening) which need to be installed using ansible-galaxy:

```
ansible-galaxy collection install devsec.hardening
```

Some variables can be set in group_vars/all/variables.yml or the inventory file but most are set in the vault encrypted host_vars/<xrootd host> file. See the host_vars/xrootd-example-host-vars.example file. Use the group_vars/all/users.yml.example as a template for adding admin users. Use the group_vars/all/xrootd_allowed_ips.yml.example as a template for restricting access to the network on port 1094.

Ansible playbook steps:

- Updates the OS and configures automatic updates
- Runs the dev-sec OS and SSH hardening roles
- Add admin users, uses the group_vars/all/users.yml file
- Installs xrootd
- Configures xrootd for use with SKA-IAM
- Generate certificates using LetsEncrypt
- Sets up share mount for xrootd data

Make sure the inventory has all the necessary varibles set then run the playbook against the just deployed server. N.B. you can do a dry-run first with the --check flag.

```
ansible-playbook xrootd.yml -i cambridge-inventory.yaml --limit <server name>
```

Different parts of the playbook can be run separately using tag(s) e.g.

```
ansible-playbook xrootd.yml -i cambridge-inventory.yaml --limit <server name> --tags install_xrootd
```

## Benchmarking the 100 Gb link

The production XRootD server serves HTTP on port 1094 over the 100Gb/s
WCDC-DIRAC link (`eth1`, `192.84.5.20/27`). The `benchmark_xrootd` role and
its client script test how much of that link is actually used. The suite is
layered so the bottleneck can be attributed correctly:

| Layer | Test | Proves |
|-------|------|--------|
| Link | server-side `ethtool` check | NIC is negotiated at 100000Mb/s full duplex |
| Network path | iperf3 (32 parallel TCP streams) | the raw path over the 100Gb IP saturates the link |
| Application | XRootD HTTP downloads | how fast the server actually serves data end-to-end |

### Server side (Ansible)

```sh
ansible-playbook xrootd.yml -i cambridge-inventory.yml --limit uksrc-cam-prod-xrootd --tags benchmark
```

This runs the 100Gb link checks (interface up, `ethtool` speed == 100000Mb/s,
IP/routing, MTU, firewalld zone and port rules) and, by default, installs and
starts an `iperf3` server bound to `192.84.5.20:5201`. Configure it with the
role variables in `roles/benchmark_xrootd/defaults/main.yml`, for example:

| Variable | Default | Purpose |
|----------|---------|---------|
| `benchmark_iface` | `eth1` | the 100Gb interface |
| `benchmark_expected_link_speed_mbps` | `100000` | speed the link must negotiate |
| `benchmark_server_ip` | `192.84.5.20` | 100Gb IP / iperf3 bind address |
| `benchmark_iperf3_port` | `5201` | iperf3 server port |
| `benchmark_iperf3_enable` | `true` | leave iperf3 running after the playbook |
| `benchmark_allow_client_ips` | `[]` | temporarily open ports for these IPs |
| `benchmark_prepare_data` | `false` | create download files under `data_path` |
| `benchmark_file_count` / `benchmark_file_size_gb` | `4` / `20` | size of the test files |
| `benchmark_data_fill` | `sparse` | `sparse` (instant zeros) or `zero` (dense) |

Only the link checks are assertions. The numeric benchmarks must run from a
client because a server cannot saturate its own NIC.

### Client side

From any machine that can reach `192.84.5.20` (the benchmark client host), run:

```sh
roles/benchmark_xrootd/files/run-benchmark-client.sh \
  -s 192.84.5.20 -p 5201 -n 32 -t 30 -f /benchmark/bench-1.bin
```

- From a host on the WCDC-DIRAC-791 network the iperf3 result measures the
  true 100Gb path.
- From the public internet (e.g. a developer workstation such as the one
  running this playbook) it measures the end-to-end path, which may be capped
  by the client's own uplink/ISP and must not be blamed on the server.
- Pass a WLCG/SKA-IAM bearer token with `-T TOKEN` for the XRootD read tests;
  reads are auth-restricted (SciTokens) so downloads without a token may be
  denied. `-r` adds a reverse (upload) test, `-u` a UDP line-rate test, `-j`
  uses 8900-byte packets for the UDP test on a jumbo-frames path.
- Thresholds can be tuned with `BENCH_NET_PASS_GBPS` (default 90) and
  `BENCH_XROOTD_PASS_GBPS` (default 10).

### Firewall note

Port 1094 is firewalled to the `xrootd_allowed_ip_addresses` list plus the
100Gb subnet, so a developer machine on a different public IP (e.g.
`86.21.218.207`) needs a temporary allowance to reach the xrootd and iperf3
ports. Add it with:

```sh
ansible-playbook xrootd.yml -i cambridge-inventory.yml --limit uksrc-cam-prod-xrootd \
  --tags benchmark -e 'benchmark_allow_client_ips=["86.21.218.207/32"]'
```

The rules are removed with `firewall-cmd` (see the comments in
`roles/benchmark_xrootd/tasks/02_firewall_allow_benchmark.yml`) - do not leave
them in place on the production host.

### Interpreting results

- **Link checks** prove the NIC exists and is negotiated at 100Gb/s full
  duplex (ethtool `Speed: 100000Mb/s`).
- **iperf3 (32 parallel TCP streams)** passing 90 Gbps proves the raw network
  path saturates the 100Gb link; a single TCP stream will usually report far
  less and is expected.
- **XRootD HTTP downloads** show what the server really serves. A gap between
  the iperf3 and HTTP numbers is expected when the storage backend (a single
  CephFS mount) is the limiting factor - it does not mean the link is slow.
