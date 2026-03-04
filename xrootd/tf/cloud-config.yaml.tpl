#cloud-config
package_reboot_if_required: true
package_update: true
package_upgrade: true
packages:
  - cloud-utils-growpart
  - e2fsprogs
  - xfsprogs
