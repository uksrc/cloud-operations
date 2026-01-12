terraform {
    required_providers {
        openstack = {
            source  = "terraform-provider-openstack/openstack"
            version = "~> 1.54"
        }
    }
}

terraform {
 backend "s3" {
   endpoint = "s3.echo.stfc.ac.uk/swift/v1"
   bucket = "tofu-state"
   key = "postgres-vm/postgres-vm.state"
   use_lockfile = false
   region = "RegionOne"
   skip_region_validation = true
   skip_credentials_validation = true
   use_path_style = true
   skip_metadata_api_check = true
 }
}

data "openstack_images_image_v2" "openstack_image" {  
    name = "ubuntu-noble-24.04-nogui"  
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

locals {
    user_map     = var.users
    primary_user = length(keys(local.user_map)) > 0 ? keys(local.user_map)[0] : ""
}

resource "openstack_compute_keypair_v2" "postgres_keys" {
    for_each   = local.user_map
    name       = "postgres-${each.key}"
    public_key = each.value
}

resource "openstack_compute_instance_v2" "postgres_vm" {
    name      = "postgres-vm"
    image_id  = data.openstack_images_image_v2.openstack_image.id
    flavor_id = data.openstack_compute_flavor_v2.vm_flavor.flavor_id
    security_groups = ["default"]
    key_pair  = length(keys(local.user_map)) > 0 ? openstack_compute_keypair_v2.postgres_keys[local.primary_user].name : null

    user_data = file("cloud-config.yaml")

    network {
        name           = "UKSRC-Network"
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