#cloud-config
package_update: true
packages:
  - cloud-utils-growpart
  - e2fsprogs
  - xfsprogs
users:
  - default
%{ for username, key in users ~}
  - name: ${username}
    gecos: ${username}
    primary_group: ${username}
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: users, admin, wheel
    lock_passwd: false
    ssh_authorized_keys:
      - ${key}
%{ endfor ~}
