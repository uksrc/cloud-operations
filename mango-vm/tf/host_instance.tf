# Provide this value via environment variable OS_CLOUD or other means

data "openstack_images_image_v2" "openstack_image" {
  name        = "ubuntu-noble-24.04-nogui"
  most_recent = true
}

data "openstack_compute_flavor_v2" "vm_flavor" {
  name = "l3.xsmall" # l3.xsmall: 60 gigs RAM, 400 DISK, 16 CORES
}

variable "primary_user" {
  description = "Username for the primary user created via cloud-init"
  type        = string
}

variable "primary_user_ssh_key" {
  description = "SSH public key for the primary user"
  type        = string
}

variable "network_cidr" {
  description = "CIDR of the internal network allowed to access the database"
  type        = string
  default     = "192.168.64.0/22"
}

variable "fixed_ip" {
  description = "Fixed IP address for the Mango VM within the internal network"
  type        = string
  default     = "192.168.64.104"
}

variable "floating_ip" {
  description = "Floating IP address for the Mango VM for external access"
  type        = string
}

resource "openstack_compute_keypair_v2" "mango_primary_key" {
  name       = "mango-${var.primary_user}"
  public_key = var.primary_user_ssh_key
}

resource "openstack_networking_secgroup_v2" "mango_sg" {
  name        = "mango-vm-sg"
  description = "Security group for Mango VM - allows internal network access"
}

resource "openstack_networking_secgroup_rule_v2" "mango_ssh" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.mango_sg.id
  description       = "Allow SSH from anywhere"
}

data "openstack_networking_network_v2" "uksrc_network" {
  name = "UKSRC-Network"
}

data "openstack_networking_subnet_v2" "uksrc_subnet" {
  network_id = data.openstack_networking_network_v2.uksrc_network.id
  cidr       = var.network_cidr
}

resource "openstack_networking_port_v2" "mango_port" {
  name           = "mango-vm-port"
  network_id     = data.openstack_networking_network_v2.uksrc_network.id
  admin_state_up = true

  fixed_ip {
    subnet_id  = data.openstack_networking_subnet_v2.uksrc_subnet.id
    ip_address = var.fixed_ip
  }

  security_group_ids = [
    openstack_networking_secgroup_v2.mango_sg.id
  ]
}

resource "openstack_compute_instance_v2" "mango_vm" {
  name      = "mango-vm"
  image_id  = data.openstack_images_image_v2.openstack_image.id
  flavor_id = data.openstack_compute_flavor_v2.vm_flavor.flavor_id
  key_pair  = openstack_compute_keypair_v2.mango_primary_key.name

  user_data = templatefile("cloud-config.yaml.tpl", {
    primary_user = var.primary_user
    primary_key  = var.primary_user_ssh_key
  })

  network {
    port = openstack_networking_port_v2.mango_port.id
  }
}

resource "openstack_networking_floatingip_associate_v2" "mango_floating_ip_assoc" {
  floating_ip = var.floating_ip
  port_id     = openstack_networking_port_v2.mango_port.id
}

output "instance_id" {
  description = "Instance ID"
  value       = openstack_compute_instance_v2.mango_vm.id
}

output "primary_user" {
  description = "Username of the primary user"
  value       = var.primary_user
}

output "primary_keypair_name" {
  description = "Name of the keypair for the primary user"
  value       = openstack_compute_keypair_v2.mango_primary_key.name
}

output "fixed_ip_address" {
  description = "Fixed internal IP address of the Mango VM"
  value       = var.fixed_ip
}

output "instance_ip_address" {
  description = "Internal IP address of the mango VM instance"
  value       = openstack_compute_instance_v2.mango_vm.access_ip_v4
}

output "external_ip_address" {
  description = "External IP address of the Mango VM instance - i.e. on the internet"
  value = openstack_networking_floatingip_associate_v2.mango_floating_ip_assoc.floating_ip
}
