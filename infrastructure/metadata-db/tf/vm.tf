# Provide this value via environment variable OS_CLOUD or other means

data "openstack_images_image_v2" "openstack_image" {
  name        = "ubuntu-noble-24.04-nogui"
  most_recent = true
}

data "openstack_compute_flavor_v2" "vm_flavor" {
  name = "l3.nano"
}

variable "users" {
  description = "Map of username -> public SSH key"
  type        = map(string)
  default     = {}
}

variable "primary_user" {
  description = "Username to use as primary user for SSH and Ansible. If not set, the first key in the users map will be used, or empty string if no users are defined."
  type        = string
  default     = ""
}

locals {
  user_map     = var.users
  primary_user = var.primary_user != "" ? var.primary_user : (length(keys(var.users)) > 0 ? keys(var.users)[0] : "")
}

resource "openstack_compute_keypair_v2" "postgres_keys" {
  for_each   = local.user_map
  name       = "postgres-${each.key}"
  public_key = each.value
}

resource "openstack_compute_instance_v2" "postgres_vm" {
  name            = "postgres-vm"
  image_id        = data.openstack_images_image_v2.openstack_image.id
  flavor_id       = data.openstack_compute_flavor_v2.vm_flavor.flavor_id
  security_groups = ["default"]
  key_pair        = length(keys(local.user_map)) > 0 ? openstack_compute_keypair_v2.postgres_keys[local.primary_user].name : null

  user_data = templatefile("cloud-config.yaml.tpl", {
    users = local.user_map
  })

  network {
    name = "UKSRC-Network"
  }
}

output "instance_id" {
  description = "Instance ID"
  value       = openstack_compute_instance_v2.postgres_vm.id
}

output "created_users" {
  description = "List of usernames created from var.users"
  value       = keys(local.user_map)
}

output "user_ssh_keys" {
  description = "Map of username => public ssh key"
  value       = local.user_map
}

output "keypair_names" {
  description = "Map of username => created OpenStack keypair name"
  value       = { for k, kp in openstack_compute_keypair_v2.postgres_keys : k => kp.name }
}

output "primary_user" {
  description = "Username chosen as primary_user (first key in the map) or empty string"
  value       = local.primary_user
}

output "primary_keypair_name" {
  description = "Name of the keypair for the primary_user, or null if none"
  value       = try(openstack_compute_keypair_v2.postgres_keys[local.primary_user].name, null)
}

output "instance_ip_address" {
  description = "IP address of the postgres VM instance"
  value       = openstack_compute_instance_v2.postgres_vm.access_ip_v4
}
