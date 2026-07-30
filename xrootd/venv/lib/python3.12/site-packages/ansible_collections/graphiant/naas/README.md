# Graphiant NaaS Ansible Collection

[![License: GPL v3+](https://img.shields.io/badge/License-GPLv3+-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/)
[![Ansible](https://img.shields.io/badge/ansible--core-2.17+-green.svg)](https://docs.ansible.com/)

The Ansible Graphiant NaaS collection includes modules for automating the management of Graphiant NaaS (Network as a Service) infrastructure.

### Ansible community package

**`graphiant.naas`** is included in the **[Ansible community package](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html)** (the curated `ansible` distribution on PyPI and in downstream OS packages). Official collection documentation - module reference, plugin index, and version metadata - is published with the rest of Ansible's community collections:

**[Graphiant.Naas - Ansible Documentation](https://docs.ansible.com/projects/ansible/latest/collections/graphiant/naas/index.html#plugins-in-graphiant-naas)**

You can still install or upgrade the collection explicitly with `ansible-galaxy collection install graphiant.naas` (for example, to pick up a newer release than the one bundled with your `ansible` install).

## Description

This collection provides Ansible modules to automate:
- Interface and circuit configuration on Edge devices
- Core (backbone) device configuration — interfaces, ISP circuits, direct-peer circuits, site info, and per-VRF syslog targets
- Static routes management (per-segment configure/deconfigure)
- VRRP (Virtual Router Redundancy Protocol) configuration
- LAG (Link Aggregation Group) interface configuration
- Interface MACsec (802.1AE) configuration and monitoring on Edge/Gateway devices
- BGP peering management (including BFD — Bidirectional Forwarding Detection)
- Site-to-Site VPN configuration (static and BGP routing)
- Global configuration objects (prefix sets, BGP filters, VPN profiles, LAN segments)
- Site management and object attachments
- Data Exchange workflows
- Raw device configuration deployment (Edge, Gateway, and Core devices)
- Edge services (DHCP subnets, DNS mode, LLDP, local web server password) on Edge/Gateway devices
- NTP Service Configuration
- Traffic Policy configuration on Edge Devices
- Prefix and Port List configuration on Edge Devices

### Key Features

- **Idempotent operations** — Deconfigure is safe to re-run and reports `changed: false` when resources are already absent. Configure can be run repeatedly; some generic modules (e.g. BGP, device config) do not compare current state and may report `changed: true` even when configuration is already applied.
- **Check mode** — Full or partial dry-run support on most modules so you can preview changes before applying
- **Jinja2 in configs** — YAML configuration files support templating for dynamic values
- **Optional detailed logging** — `detailed_logs` parameter for debugging and troubleshooting
- **Ansible standards** — FQCNs, shared auth documentation, and [Ansible Collection Inclusion Checklist](https://github.com/ansible-collections/ansible-inclusion/blob/main/collection_checklist.md) compliance

## Support & Compatibility

| Component | Requirement |
|-----------|-------------|
| **Collection version** | 26.6.0 (current stable) |
| **ansible-core** | >= 2.17.0 (tested with 2.17, 2.18, 2.19, 2.20) |
| **Python** | >= 3.7 |
| **Graphiant SDK** | >= 26.6.0 | 

> **Note:** All dependency versions are managed centrally in `_version.py`. See [Version Management Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md) for details.

> **Authentication:** Configure `GRAPHIANT_HOST`, **`graphiant login`** + `GRAPHIANT_ACCESS_TOKEN`, or username/password — follow **[Graphiant API Authentication](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main?tab=readme-ov-file#graphiant-api-authentication)** in the graphiant-playbooks repository README, then use this collection's [Credential Management Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md) for module-specific options.

## Included Content

### [Modules](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main/ansible_collections/graphiant/naas#modules)

| Name | Description |
|------|-------------|
| `graphiant_device_system` | Configure device (Edge, Gateway or Core) hostname, region, and site |
| `graphiant_edge_services` | Configure Edge/Gateway services (DHCP, DNS, LLDP, local web server password) |
| `graphiant_interfaces` | Manage interfaces and circuits (LAN/WAN) on Edge devices |
| `graphiant_backbone` | Manage Graphiant Core (backbone) device interfaces, ISP circuits, direct-peer circuits, site info, and per-VRF syslog targets |
| `graphiant_static_routes` | Manage static routes (per-segment configure/deconfigure/validate) |
| `graphiant_vrrp` | Manage VRRP (Virtual Router Redundancy Protocol) configuration |
| `graphiant_lag_interfaces` | Manage LAG interfaces configuration |
| `graphiant_macsec` | Configure interface MACsec (802.1AE) on Edge/Gateway devices |
| `graphiant_macsec_info` | Query MACsec monitoring status (secure/unsecure) per interface |
| `graphiant_bgp` | Manage BGP peering and routing policies (including BFD) |
| `graphiant_site_to_site_vpn` | Manage Site-to-Site VPN (static and BGP routing) on edge devices |
| `graphiant_global_config` | Manage global configuration objects |
| `graphiant_sites` | Manage sites and site attachments |
| `graphiant_data_exchange` | Manage Data Exchange workflows (create/update/delete services and customers, match, accept invitation).|
| `graphiant_data_exchange_info` | Query Data Exchange info (services summary, customers summary, service health) |
| `graphiant_device_config` | Push raw device configurations to Edge, Gateway, and Core devices |
| `graphiant_ntp` | Manage NTP objects |
| `graphiant_traffic_policy` | Manage device traffic policy rulesets and LAN segment attachments (configure workflow: rulesets + attach; deconfigure workflow: detach + delete) |
| `graphiant_security_policy` | Manage device security policy rulesets and zone pair attachments (configure workflow: rulesets + attach_to_zone_pairs; deconfigure workflow: detach_from_zone_pairs + delete) |
| `graphiant_prefix_port_list` | Manage Prefix & Port Lists on Edge devices | 

## Installation

### Windows (WSL)

Ansible does not run natively on Windows. Use **Windows Subsystem for Linux (WSL)** to get a full Linux environment, then follow the standard installation steps.

**Step 1 — Install WSL**

Open PowerShell as Administrator and run:
```powershell
wsl --install
```
This installs **Ubuntu** as the default distribution. Restart when prompted. After reboot, open the Ubuntu terminal and create your username and password.
More info: [Install WSL | Microsoft Learn](https://learn.microsoft.com/en-us/windows/wsl/install)

**Step 2 — Update Linux and install Python**

In your WSL Ubuntu terminal:
```bash
sudo apt update && sudo apt upgrade -y && sudo apt install python3 python3-pip python3-venv -y
```

**Step 3 — Create a project directory**

```bash
mkdir ~/ansible-workspace && cd ~/ansible-workspace
```

**Step 4 — Install the collection**

Continue with the **[From Source](#from-source)** or **[From Ansible Galaxy](#from-ansible-galaxy)** steps below inside the WSL terminal.

---

### From Source

**Option A — Clone with Git:**

```bash
git clone https://github.com/Graphiant-Inc/graphiant-playbooks.git
cd graphiant-playbooks

# Create virtual environment or activate an existing virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install collection dependencies
pip install -r ansible_collections/graphiant/naas/requirements-ee.txt

# Install collection from source
pip install ansible-core
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force
```

**Option B — Download ZIP (no Git required):**

1. Open [https://github.com/Graphiant-Inc/graphiant-playbooks](https://github.com/Graphiant-Inc/graphiant-playbooks) in your browser.
2. Click the **Code** dropdown → **Download ZIP**.
3. Unzip the downloaded file and enter the directory:

```bash
unzip graphiant-playbooks-main.zip
cd graphiant-playbooks-main
```

Then continue with the same steps as Option A (create a virtual environment, install dependencies, install the collection).


### From Ansible Galaxy

```bash
# Install collection dependencies in a virtual environment
pip install -r ansible_collections/graphiant/naas/requirements-ee.txt

# Install collection from Ansible Galaxy
ansible-galaxy collection install graphiant.naas
```

### Verify Installation

```bash
ansible-galaxy collection list graphiant.naas
```

### Test Installation (E2E Integration Test)

Test the installed collection by running the `hello_test.yml` playbook. This test is also run automatically in CI/CD as the E2E integration test when GRAPHIANT credentials are configured:

```bash
# Set environment variables (password login)
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

# Alternatively, sign in with the Graphiant CLI (SSO) and load credentials into the shell:
#   graphiant login && source ~/.graphiant/env.sh
# That exports GRAPHIANT_ACCESS_TOKEN; the collection prefers the bearer token over username/password when set.

# Optional: Enable pretty output for detailed_logs
export ANSIBLE_STDOUT_CALLBACK=debug

# Run test playbook
ansible-playbook ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/hello_test.yml
```

The `hello_test.yml` playbook:
- Tests module loading with check_mode (no API calls)
- Tests actual API connectivity and configuration
- Shows detailed logs when `detailed_logs: true`
- Warns if `ANSIBLE_STDOUT_CALLBACK` is not set to `debug`

### Validation and Linting

**Validate collection structure:**
```bash
# From repository root
python scripts/validate_collection.py

# Or from collection directory
python ../../scripts/validate_collection.py
```

**Build collection (for distribution):**
```bash
# Using ansible-galaxy
ansible-galaxy collection build ansible_collections/graphiant/naas/

# Or using build script (from repository root)
python scripts/build_collection.py
```

**Linting tools (run locally):**
```bash
# Install development tools needed for linting
source venv/bin/activate
pip install black flake8 pylint djlint ansible-lint pre-commit

# Python code formatting check with black (runs in CI)
black ansible_collections/graphiant/naas/plugins/ -l 120 --check

# Python code formatting with black if required
black ansible_collections/graphiant/naas/plugins/ -l 120 --check --diff
black ansible_collections/graphiant/naas/plugins/ -l 120

# Python linting with flake8 (runs in CI)
flake8 ansible_collections/graphiant/naas/ --max-line-length=120

# Python linting with pylint (runs in CI)
export PYTHONPATH=$PYTHONPATH:$(pwd)/ansible_collections/graphiant/naas/plugins/
pylint --errors-only ansible_collections/graphiant/naas/plugins/

# Ansible playbook linting (runs in CI, requires collection to be installed first)
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force
ansible-lint --config-file ~/.ansible/collections/ansible_collections/graphiant/naas/.ansible-lint ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/

# YAML/Jinja template linting (runs in CI)
djlint ansible_collections/graphiant/naas/configs -e yaml
djlint ansible_collections/graphiant/naas/templates -e yaml
```

**Antsibull documentation validation (runs in CI):**
```bash
# Install antsibull-docs
pip install antsibull-docs antsibull-changelog

# Validate module documentation
antsibull-docs lint-collection-docs ansible_collections/graphiant/naas/

# Vaidate changelog documentation
antsibull-changelog lint-changelog-yaml ansible_collections/graphiant/naas/changelogs/changelog.yaml
```

**Note:** CI/CD runs the **`python-lint`** job (`black --check` at line length 120, `flake8` with `--max-line-length=120`, and `pylint --errors-only`) on `ansible_collections/graphiant/naas/plugins/`, plus `ansible-lint`, `djlint`, `antsibull-docs` / changelog lint, `ansible-test` sanity, and the Ansible inclusion checklist. For local development, optional **pre-commit** hooks at the repository root (see `.pre-commit-config.yaml`) run `flake8` and `pylint` on the same plugin tree when configured. See `.github/workflows/README.md` for workflow details.

## Using This Collection

For detailed usage examples and per-module playbook walkthroughs, see the **[Examples Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/EXAMPLES.md)**.

### Example Playbook

```yaml
---
- name: Configure Graphiant network
  hosts: localhost
  gather_facts: false
  vars:
    graphiant_client_params: &graphiant_client_params
      host: "{{ graphiant_host | default(lookup('env', 'GRAPHIANT_HOST')) }}"
      username: "{{ graphiant_username | default(lookup('env', 'GRAPHIANT_USERNAME')) }}"
      password: "{{ graphiant_password | default(lookup('env', 'GRAPHIANT_PASSWORD')) }}"

  tasks:
    - name: Configure LAN interfaces only
      graphiant.naas.graphiant_interfaces:
        <<: *graphiant_client_params
        interface_config_file: "sample_interface_config.yaml"
        operation: "configure_lan_interfaces"
        detailed_logs: true
        state: present
      tags: ['interfaces', 'lan']
      register: configure_result

    - name: Display LAN Interface Configuration Results
      ansible.builtin.debug:
        msg: "{{ configure_result.msg }}"
      when: configure_result is defined and configure_result.msg is defined
      tags: ['interfaces', 'lan']

    - name: Configure edge services (DHCP, DNS, LLDP)
      graphiant.naas.graphiant_edge_services:
        <<: *graphiant_client_params
        edge_services_config_file: "sample_edge_services.yaml"
        operation: configure
        detailed_logs: true
        state: present
      register: edge_services_result
      tags: ['edge_services']

    - name: Display edge services result
      ansible.builtin.debug:
        msg: "{{ edge_services_result.msg }}"
      when: edge_services_result is defined and edge_services_result.msg is defined
      tags: ['edge_services']

    - name: Configure MACsec from YAML (Vault CAK secrets)
      graphiant.naas.graphiant_macsec:
        <<: *graphiant_client_params
        macsec_config_file: "sample_macsec.yaml"
        vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
        operation: configure
        detailed_logs: true
        state: present
      register: macsec_result
      no_log: true
      tags: ['macsec']

    - name: Display MACsec result
      ansible.builtin.debug:
        msg: "{{ macsec_result.msg }}"
      when: macsec_result is defined and macsec_result.msg is defined
      tags: ['macsec']

    - name: Configure global prefix sets
      graphiant.naas.graphiant_global_config:
        <<: *graphiant_client_params
        config_file: "sample_global_prefix_lists.yaml"
        operation: "configure"
        detailed_logs: true
        state: present
      register: prefix_sets_result
      tags: ['global_config', 'prefix_sets']

    - name: Display prefix sets result
      ansible.builtin.debug:
        msg: "{{ prefix_sets_result.msg }}"
      tags: ['global_config', 'prefix_sets']

    - name: Configure global BGP filters
      graphiant.naas.graphiant_global_config:
        <<: *graphiant_client_params
        config_file: "sample_global_bgp_filters.yaml"
        operation: "configure"
        detailed_logs: true
        state: present
      register: bgp_filters_result
      tags: ['global_config', 'bgp_filters']

    - name: Display BGP filters result
      ansible.builtin.debug:
        msg: "{{ bgp_filters_result.msg }}"
      tags: ['global_config', 'bgp_filters']

    - name: Configure BGP peering
      graphiant.naas.graphiant_bgp:
        <<: *graphiant_client_params
        bgp_config_file: "sample_bgp_peering.yaml"
        operation: "configure"
        detailed_logs: true
        state: present
      ignore_errors: true
      register: bgp_peering_result
      tags: ['bgp', 'peering']

    - name: Display BGP peering result
      ansible.builtin.debug:
        msg: "{{ bgp_peering_result.msg }}"
      tags: ['bgp', 'peering']

    - name: Configure full backbone (Core) settings
      graphiant.naas.graphiant_backbone:
        <<: *graphiant_client_params
        config_yaml_file: "sample_backbone_config.yaml"
        operation: "configure"
        detailed_logs: true
      tags: ['backbone']
```

### Example Playbooks

The collection includes ready-to-use example playbooks in the `playbooks/` directory:

| Playbook | Description |
|----------|-------------|
| `hello_test.yml` | E2E integration test playbook (used in CI/CD) |
| `complete_network_setup.yml` | Full network configuration workflow |
| `interface_management.yml` | Interface and circuit operations |
| `backbone_management.yml` | Core (backbone) device management operations |
| `static_routes_management.yml` | Static routes configure/deconfigure/validate |
| `vrrp_interface_management.yml` | VRRP configuration on interfaces and subinterfaces |
| `lag_interface_management.yml` | LAG interface configuration |
| `macsec_management.yml` | Interface MACsec configuration and monitoring status |
| `circuit_management.yml` | Circuit configuration and static routes |
| `lan_segments_management.yml` | LAN segment configuration |
| `site_management.yml` | Site creation and management |
| `site_to_site_vpn.yml` | Site-to-Site VPN create/delete (uses Ansible Vault for preshared keys) |
| `site_lists_management.yml` | Site list operations |
| `credential_examples.yml` | Credential management examples |
| `device_config_management.yml` | Push raw device configurations (Edge/Gateway/Core) |
| `ntp_management.yml` | NTP configuration (global and device) |
| `device_system_management.yml` | Device name, region, and site configuration |
| `edge_services_management.yml` | Edge DHCP, DNS, LLDP, local web server password (Vault-supported) |
| `test_collection.yml` | Collection validation and testing |
| `traffic_policies_management.yml` | Traffic policies and LAN-segment attachments |
| `security_policies_management.yml` | Security policies and zone-pair attachments |
| `prefix_port_list_management.yml` | Prefix and port lists | 

#### Data Exchange Workflows

The `playbooks/de_workflows/` directory contains playbooks for Data Exchange operations:

| Playbook | Description |
|----------|-------------|
| `00_dataex_*_prerequisites.yml` | Prerequisites setup (LAN interfaces, segments, VPN profiles) |
| `01_dataex_create_services.yml` | Create Data Exchange services. Supports `--check` and `--check --diff` |
| `01b_dataex_update_services.yml` | Update `prefixTags` on existing services. Supports `--check --diff` |
| `02_dataex_create_customers.yml` | Create Data Exchange customers. Supports `--check --diff` to detect `adminEmail` drift on existing customers. Custom config: `-e config_file=...` |
| `02b_dataex_update_customers.yml` | Update `adminEmail` on existing customers. Supports `--check --diff` |
| `03_dataex_match_services_to_customers.yml` | Match services to customers; saves match responses to `output/`. Custom config: `-e config_file=...` |
| `04_dataex_delete_customers.yml` | Delete customers (idempotent — already-absent customers are skipped) |
| `05_dataex_delete_services.yml` | Delete services (idempotent — already-absent services are skipped) |
| `07_dataex_accept_invitation.yml` | Accept service invitations. Supports `--check`. Configures multi-peer IPSec gateways via `ipsecGatewayPeers` (requires `graphiant_sdk >= 26.6.0`). Custom config: `-e config_file=...`. Optional matches file: `-e matches_file=...` (required when service is not yet visible via API in the consumer tenant) |
| `08_dataex_query_service_health.yml` | Query service health monitoring |

**Modules used:**
- `graphiant_data_exchange` - Manage services, customers, matches, and invitations
- `graphiant_data_exchange_info` - Query services summary, customers summary, and service health

### Module Documentation

View module documentation with `ansible-doc`:

```bash
ansible-doc graphiant.naas.graphiant_interfaces
ansible-doc graphiant.naas.graphiant_static_routes
ansible-doc graphiant.naas.graphiant_ntp
ansible-doc graphiant.naas.graphiant_traffic_policy
ansible-doc graphiant.naas.graphiant_security_policy
ansible-doc graphiant.naas.graphiant_device_system
ansible-doc graphiant.naas.graphiant_edge_services
ansible-doc graphiant.naas.graphiant_vrrp
ansible-doc graphiant.naas.graphiant_lag_interfaces
ansible-doc graphiant.naas.graphiant_macsec
ansible-doc graphiant.naas.graphiant_macsec_info
ansible-doc graphiant.naas.graphiant_bgp
ansible-doc graphiant.naas.graphiant_site_to_site_vpn
ansible-doc graphiant.naas.graphiant_global_config
ansible-doc graphiant.naas.graphiant_sites
ansible-doc graphiant.naas.graphiant_data_exchange
ansible-doc graphiant.naas.graphiant_data_exchange_info
ansible-doc graphiant.naas.graphiant_device_config
ansible-doc graphiant.naas.graphiant_backbone
ansible-doc graphiant.naas.graphiant_prefix_port_list.py
```

## Documentation

### Quick Links

- **[Graphiant API Authentication](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main?tab=readme-ov-file#graphiant-api-authentication)** — graphiant CLI login, `GRAPHIANT_HOST`, `GRAPHIANT_ACCESS_TOKEN`, and portal credentials (graphiant-playbooks repo README)
- **[Examples Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/EXAMPLES.md)** - Detailed usage examples and playbook samples
- **[Credential Management Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md)** - Best practices for managing credentials securely
- **[Version Management Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md)** - Version management system and quick reference
- **[Release Process](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/RELEASE.md)** - Complete release process documentation
- **[Documentation Index](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/README.md)** - Full documentation structure

### Additional Documentation

- **Module Documentation**: Use `ansible-doc` to view embedded module documentation (see above)
- **Docusite Setup**: See [docs/DOCSITE_SETUP.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/DOCSITE_SETUP.md) for building HTML documentation
- **Changelog**: See [changelogs/changelog.yaml](changelogs/changelog.yaml) for version history and release notes

### Credential Management

**Recommended: Use YAML anchors** to avoid repetition:

```yaml
vars:
  graphiant_client_params: &graphiant_client_params
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

tasks:
  - name: Configure interfaces
    graphiant.naas.graphiant_interfaces:
      <<: *graphiant_client_params
      interface_config_file: "config.yaml"
      operation: "configure_lan_interfaces"
```

**Other options:**
- Environment variables (`GRAPHIANT_HOST`, `GRAPHIANT_USERNAME`, `GRAPHIANT_PASSWORD`)
- Ansible Vault for encrypted credentials
- Variable files with `vars_files`

See [Credential Management Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md) for detailed examples. For environment setup (CLI login, token export), see [Graphiant API Authentication](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main?tab=readme-ov-file#graphiant-api-authentication) in the graphiant-playbooks README.

### State Parameter

All modules support `state` parameter:
- `present`: Configure/create resources (maps to `configure` operation)
- `absent`: Deconfigure/remove resources (maps to `deconfigure` operation)
- When both `operation` and `state` are provided, `operation` takes precedence

`graphiant_device_system` and `graphiant_edge_services` accept only `present` / configure; they do not support `absent`.

### Check Mode

Use `ansible-playbook ... --check` or set `check_mode: true` on a task to run without committing mutating API calls where the module supports it. Declared support is under `attributes.check_mode` in `ansible-doc graphiant.naas.<module_name>`.

| Support | Modules | Behavior |
|--------|---------|----------|
| **Full** | `graphiant_interfaces`, `graphiant_vrrp`, `graphiant_lag_interfaces`, `graphiant_sites`, `graphiant_site_to_site_vpn`, `graphiant_global_config`, `graphiant_static_routes`, `graphiant_ntp`, `graphiant_device_system`, `graphiant_edge_services`, `graphiant_macsec`, `graphiant_data_exchange`, `graphiant_data_exchange_info`, `graphiant_prefix_port_list`, `graphiant_traffic_policy`, `graphiant_security_policy` | Mutating writes are skipped. Intended requests are usually logged with a `[check_mode]` prefix; use `detailed_logs: true` and often `ANSIBLE_STDOUT_CALLBACK=debug` for readable output. |
| **Partial** | `graphiant_bgp`, `graphiant_device_config`, `graphiant_backbone`                                                                                                                                                                                                                                                                    | Writes are still skipped, but `changed` is not computed from a full live diff: BGP reports `changed: true` for configure/deconfigure/detach in check mode; `graphiant_device_config` returns `changed: false` for `show_validated_payload` and `changed: true` for `configure`; `graphiant_backbone` reports `changed: true` whenever the supplied config file contains matching backbone resources (no live diff against current Core device state). See each module's `attributes.check_mode` details. |
| **Read-only** | `graphiant_macsec_info` | Always read-only; check mode has no side effects. |

**Full-mode nuances:** `graphiant_device_system`, `graphiant_edge_services`, `graphiant_macsec`, `graphiant_traffic_policy`, and `graphiant_security_policy` read device state in check mode and set `changed` from whether an apply would be needed. For LWS, omit `localWebServerPasswordForce` after a successful set—force re-pushes every run because the portal stores a hash. `graphiant_data_exchange_info` and `graphiant_macsec_info` are always read-only. `graphiant_data_exchange` skips mutating writes in check mode; see that module's `attributes.check_mode` for details.

**Diff mode (`--diff`):** `graphiant_device_system`, `graphiant_edge_services`, `graphiant_prefix_port_list`, `graphiant_macsec`, `graphiant_traffic_policy`, `graphiant_security_policy`, `graphiant_data_exchange`, `graphiant_ntp`, `graphiant_static_routes`, and `graphiant_site_to_site_vpn` support `--diff`. Use `--check --diff` or `--diff` to see `before`/`after` and `details.diff_plan`. For `graphiant_data_exchange`, diff is available for `create_services`, `update_services`, `create_customers`, and `update_customers`; in `--check --diff` mode, `create_customers` also surfaces `adminEmail` drift on existing customers with a hint to use `update_customers`. For `graphiant_site_to_site_vpn`, secrets (`presharedKey`, `md5Password`) are redacted in diff output.

**Example: run playbooks in check mode (dry run)**

```bash
ansible-playbook playbooks/interface_management.yml --check
ansible-playbook playbooks/complete_network_setup.yml --check
ansible-playbook playbooks/device_system_management.yml --tag configure -e config_file=sample_device_system.yaml --check --diff
ansible-playbook playbooks/edge_services_management.yml --tags configure_without_vault -e config_file=sample_edge_services.yaml --check --diff
# LWS via vault: use --tags configure and --vault-password-file (see edge_services_management.yml)
ansible-playbook playbooks/macsec_management.yml --tags configure -e config_file=sample_macsec.yaml --check --diff --vault-password-file configs/vault-password-file.sh
# CAK via vault required for configure tag; use configure_without_vault only with plaintext cak in YAML (dev/local)

ansible-playbook playbooks/ntp_management.yml --tags configure --check --diff
ansible-playbook playbooks/static_routes_management.yml --tags configure --check --diff
ansible-playbook playbooks/site_to_site_vpn.yml --tag create --check --diff --vault-password-file configs/vault-password-file.sh
# Data Exchange: check + diff to preview creates and detect adminEmail drift on existing customers
ansible-playbook playbooks/de_workflows/02_dataex_create_customers.yml --check --diff
# Data Exchange: validate accept_invitation before applying (provide matches_file if service not visible via API)
ansible-playbook playbooks/de_workflows/07_dataex_accept_invitation.yml --check \
  -e matches_file=de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json
```

**Example: single task in check mode**

```yaml
- name: Preview LAN interface configuration (no changes made)
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    operation: "configure_lan_interfaces"
  check_mode: true
  register: preview

# With detailed_logs and ANSIBLE_STDOUT_CALLBACK=debug you will see [check_mode] payloads in output
```

**Example: read-only query (check mode safe)**

```yaml
- name: Query Data Exchange service health (module is read-only)
  graphiant.naas.graphiant_data_exchange_info:
    <<: *graphiant_client_params
    query: service_health
    service_name: "{{ data_exchange_service_name }}"
  check_mode: true
```

For the authoritative wording on each module, see `ansible-doc graphiant.naas.<module_name>` (especially `attributes.check_mode`).

### Idempotency

Modules are designed to be idempotent where possible and to report `changed` accurately.

**Recent behavior (TE-4366 and related):**
- **Deconfigure operations**: Idempotent and safe to run multiple times. When a resource is already absent or "object not found", the module reports `changed: false` and does not fail.
- **Structured results**: Manager methods return results with `changed`, `created`, `skipped`, and `deleted` so playbooks can react to what actually happened.
- **Interface and circuit modules**: Deconfigure logic (e.g. `deconfigure_lan_interfaces`, `deconfigure_circuits`, `deconfigure_wan_circuits_interfaces`) correctly reports `changed: false` when there is nothing to remove; static route cleanup and circuit removal order are handled so repeated runs stay safe.
- **Configure operations**: Many configure operations (e.g. full interface or BGP push) do not perform a full state comparison before applying. They push the desired config and may report `changed: true` even if the device is already in that state. This is documented in the relevant modules.
- **Traffic and security policies**: `graphiant_traffic_policy` and `graphiant_security_policy` compare intended rulesets (and segment or zone-pair attachments) to live device state and skip the push when already matched.  Use `--check` to preview whether changes would be made and `--diff` to see per-rule deltas in `details.diff_plan`.
- **Data Exchange operations**: All Data Exchange operations are idempotent. `create_services` and `create_customers` skip already-existing resources (`changed: false`, `skipped` non-empty). `match_service_to_customers` skips already-matched pairs. `delete_customers` and `delete_services` skip already-absent resources. `accept_invitation` skips already-linked consumers. Re-running any workflow playbook is safe.

**Summary:**
- Run deconfigure and Data Exchange delete tasks repeatedly without concern; they are idempotent.
- For configure tasks, re-running may report `changed: true` depending on the module and operation; see module docs for details.

### Detailed Logging

All modules support `detailed_logs` parameter:
- `true`: Show detailed library logs in task output
- `false`: Show only basic success/error messages (default)

```yaml
- name: Configure with detailed logs
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "config.yaml"
    operation: "configure_lan_interfaces"
    detailed_logs: true
```

For readable output (removes `\n` characters), set:
```bash
export ANSIBLE_STDOUT_CALLBACK=debug
```

### Python Library Usage

The collection can also be used as a Python library:

```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/collection_root/ansible_collections/graphiant/naas/plugins/module_utils:$PYTHONPATH
```

```python
from libs.graphiant_config import GraphiantConfig

config = GraphiantConfig(
    base_url="https://api.graphiant.com",
    username="user",
    password="pass"
)
config.interfaces.configure_lan_interfaces("interface_config.yaml")
```

See `tests/test.py` for comprehensive Python library usage examples.

### Running Tests

The test suite (`tests/test.py`) requires `GRAPHIANT_HOST` and either `GRAPHIANT_ACCESS_TOKEN` or `GRAPHIANT_USERNAME` and `GRAPHIANT_PASSWORD`:

```bash
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

# Alternatively, sign in with the Graphiant CLI (SSO) and load credentials into the shell:
#   graphiant login && source ~/.graphiant/env.sh
# That exports GRAPHIANT_ACCESS_TOKEN; the collection prefers the bearer token over username/password when set.

# From repo root (recommended): set PYTHONPATH then run
export PYTHONPATH=$PYTHONPATH:$(pwd)/ansible_collections/graphiant/naas/plugins/module_utils
python ansible_collections/graphiant/naas/tests/test.py

# Or from the collection directory
cd ansible_collections/graphiant/naas
python -m unittest tests.test
```

**Offline unit tests** (no Graphiant API) use `ansible-test units` and mock dependencies. They run in the **`test` workflow job** in the [Test Collection](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/.github/workflows/test.yml) workflow (step **Run ansible-test units**) and improve code coverage for `plugins/module_utils` without live credentials:

```bash
cd ansible_collections/graphiant/naas
pip install -r requirements-ee.txt -r tests/unit/requirements.txt
ansible-test units --local --python 3.12
```

**Note:** The `test.ini` configuration file has been removed. All tests now use environment variables for credential management, which is more secure and aligns with CI/CD best practices.

## Configuration Files

Configuration files use YAML format with optional Jinja2 templating. Sample files are in the `configs/` directory:

- `sample_interface_config.yaml` - Interface configurations
- `sample_static_route.yaml` - Static routes (per-segment) configuration
- `sample_device_ntp.yaml` - NTP objects under `edge.ntpGlobalObject`
- `sample_device_traffic_policies.yaml` - Traffic rulesets under `edge.trafficPolicy` and LAN segment ruleset attachments under `edge.segments` (use configure + attach_to_lan_segments, or the `traffic_policies_management.yml` playbook `--tags configure`)
- `sample_device_security_policies.yaml` - Security rulesets under `edge.trafficPolicy.securityRulesets` and zone pair ruleset attachments under `edge.trafficPolicy.zones` (use configure + attach_to_zone_pairs, or the `security_policies_management.yml` playbook `--tags configure`). Custom application matches (`applicationCustom`) require DPI applications from `graphiant_edge_services` / `sample_edge_services.yaml`.
- `sample_vrrp_config.yaml` - VRRP (Virtual Router Redundancy Protocol) configurations
- `sample_lag_interface_config.yaml` - LAG interface configurations
- `sample_macsec.yaml` - Interface MACsec (PSK/SAK) configuration; CAK via `vault_devices_macsec_psk` in `vault_secrets.yml`
- `sample_bgp_peering.yaml` - BGP peering configurations
- `sample_global_*.yaml` - Global configuration objects
- `sample_device_config_payload.yaml` - Raw device configuration payloads (Edge/Gateway Device types)
- `sample_device_config_core_device_payload.yaml` - Raw device configuration payloads (Core Device type)
- `sample_device_config_with_template.yaml` - Device config with user-defined template (`device_config_template.yaml`)
- `sample_backbone_config.yaml` - Core (backbone) device configuration covering interfaces (loopback, core_link, ipsec_tunnel, p2mp_tunnel, isp_circuit, direct_peer, disabled), site info, and per-VRF syslog targets
- `sample_sites.yaml` - Site configurations
- `sample_prefix_and_port_list.yaml` - Network Prefix and Port configuration

### Config File Path Resolution

Config file paths are resolved in the following order:

1. **Absolute path**: If an absolute path is provided, it is used directly
2. **GRAPHIANT_CONFIGS_PATH**: If set, uses this path directly as the configs directory
3. **Collection's configs folder**: By default, looks in the collection's `configs/` folder. Find the collection location with:
   ```bash
   ansible-galaxy collection list graphiant.naas
   ```
4. **Fallback**: If configs folder cannot be located, falls back to `configs/` in current working directory

Similarly, template paths use `GRAPHIANT_TEMPLATES_PATH` environment variable.

Check `logs/log_<date>.log` under the playbook working directory (for example `playbooks/logs/`). Secrets are already masked in Ansible output (`no_log` on modules and tasks, plus vault). Outside Ansible, collection log output masks API keys listed in `_SENSITIVE_LOG_KEYS` in `device_config_common.py` (see [Credential Management Guide](docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md#logging)). Do not commit log files.

Data Exchange configurations are in `configs/de_workflows_configs/`.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](../../CONTRIBUTING.md) for:
- Development setup
- Code standards
- Testing requirements
- Pull request process

## Release Notes

See [changelogs/changelog.yaml](changelogs/changelog.yaml) for version history and release notes.

## Version Management

Version information is centralized in `_version.py`. To bump versions or update dependencies, see [Version Management Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md) and [Release Process](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/RELEASE.md) for detailed instructions.

Quick version bump:
```bash
# From repository root
# Patch release (bug fixes)
python scripts/bump_version.py patch

# Minor release (new features)
python scripts/bump_version.py minor

# Major release (breaking changes)
python scripts/bump_version.py major

# Set specific version
python scripts/bump_version.py 26.4.0
```

After bumping version, remember to:
1. Update `changelogs/changelog.yaml` with actual changes (or use antsibull-changelog fragments)
2. Install dependencies: `pip install -r requirements-ee.txt`
3. Review and commit changes

## Support

- **Documentation**: [docs.graphiant.com](https://docs.graphiant.com/)
- **Issues**: [GitHub Issues](https://github.com/Graphiant-Inc/graphiant-playbooks/issues)
- **Email**: [support@graphiant.com](mailto:support@graphiant.com)

## License

GNU General Public License v3.0 or later (GPLv3+) - see [LICENSE](LICENSE) for details.
