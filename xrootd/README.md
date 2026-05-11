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
Some variables can be set in group_vars/all/variables.yml or the inventory file but most are set in the vault encrypted host_vars/<xrootd host> file. See the host_vars/xrootd-example-host-vars.example file. Use the group_vars/all/users.yml.example as a template for adding admin users.

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
ansible-playbook xrootd.yml -i inventory.yaml --limit <server name>
```
Different parts of the playbook can be run separately using tag(s) e.g.
```
ansible-playbook xrootd.yml -i inventory.yaml --limit <server name> --tags install_xrootd
```
