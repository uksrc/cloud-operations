data "openstack_images_image_v2" "xrootd_image" {
  name        = var.openstack_image
  most_recent = true
}

data "openstack_compute_flavor_v2" "xrootd_flavor" {
  name = var.openstack_flavor
}

data "openstack_compute_keypair_v2" "xrootd_keypair" {
  name = var.environment
}

data "openstack_networking_network_v2" "ska_uksrc_network" {
  name = var.openstack_ska_uksrc_network
}

data "openstack_networking_subnet_v2" "ska_uksrc_subnet" {
  network_id = data.openstack_networking_network_v2.ska_uksrc_network.id
  name       = var.openstack_ska_uksrc_subnet
}

data "openstack_networking_network_v2" "ska_uksrc_network_wcdc_dirac" {
  name = var.openstack_wcdc_dirac_network
}

data "openstack_networking_network_v2" "iris_network" {
  name = var.openstack_iris_network
}

resource "openstack_networking_secgroup_v2" "ska_uksrc_xrootd_sg" {
  name        = "${var.environment}-sg"
  description = "XRootD server access at Cambridge"
}

resource "openstack_networking_secgroup_rule_v2" "ssh_access" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = data.openstack_networking_subnet_v2.ska_uksrc_subnet.cidr
  security_group_id = openstack_networking_secgroup_v2.ska_uksrc_xrootd_sg.id
  description       = "Allow SSH from internal network"
}

# UKSRC port
resource "openstack_networking_port_v2" "uksrc_port" {
  name           = "${var.environment}-uksrc"
  network_id     = data.openstack_networking_network_v2.ska_uksrc_network.id
  admin_state_up = "true"
  lifecycle {
    prevent_destroy = true
  }
  security_group_ids = [
    openstack_networking_secgroup_v2.ska_uksrc_xrootd_sg.id
  ]
}

# 100Gb WCDC DIRAC SRIOV port
resource "openstack_networking_port_v2" "ska_uksrc_wcdc_dirac_sriov_port" {
  name           = "${var.environment}-wcdc-dirac-sriov"
  network_id     = data.openstack_networking_network_v2.ska_uksrc_network_wcdc_dirac.id
  admin_state_up = "true"

  binding {
    vnic_type = "direct"
  }
  lifecycle {
    prevent_destroy = true
  }
}

# IRIS SRIOV port
resource "openstack_networking_port_v2" "iris_sriov_port" {
  name           = "${var.environment}-iris-sriov"
  network_id     = data.openstack_networking_network_v2.iris_network.id
  admin_state_up = "true"
  binding {
    vnic_type = "direct"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "openstack_compute_instance_v2" "xrootd_instance" {

  name      = var.environment
  image_id  = data.openstack_images_image_v2.xrootd_image.id
  flavor_id = data.openstack_compute_flavor_v2.xrootd_flavor.flavor_id
  key_pair  = data.openstack_compute_keypair_v2.xrootd_keypair.name

  user_data = templatefile("cloud-config.yaml.tpl", {
    default_username = var.default_username
  })

  network {
    port = openstack_networking_port_v2.uksrc_port.id
  }
  network {
    port = openstack_networking_port_v2.ska_uksrc_wcdc_dirac_sriov_port.id
  }
  network {
    port = openstack_networking_port_v2.iris_sriov_port.id
  }
}
