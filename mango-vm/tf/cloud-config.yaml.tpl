#cloud-config
package_update: true
packages:
  - cloud-utils-growpart
  - e2fsprogs
  - xfsprogs
users:
  - default
%{ if primary_user != "" ~}
  - name: ${primary_user}
    gecos: ${primary_user}
    primary_group: ${primary_user}
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: users, admin, wheel
    lock_passwd: false
    ssh_authorized_keys:
      - ${primary_key}
%{ endif ~}
