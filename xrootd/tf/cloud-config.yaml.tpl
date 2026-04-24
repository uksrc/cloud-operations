#cloud-config

# override the default user e.g. rocky
# gets the openstack keypair
user:
  name: ${default_username}
  lock_passwd: True
  gecos: UKSRC XRootD Cloud User
  groups: [adm, systemd-journal]
  sudo: ["ALL=(ALL) NOPASSWD:ALL"]
  shell: /bin/bash

package_reboot_if_required: true
package_update: true
package_upgrade: true
packages:
  - cloud-utils-growpart
  - e2fsprogs
  - xfsprogs
  - python3.12
