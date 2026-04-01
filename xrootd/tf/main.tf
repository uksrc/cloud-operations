data "openstack_images_image_v2" "xrootd_image" {
  name        = var.openstack_image
  most_recent = true
}

data "openstack_compute_flavor_v2" "xrootd_flavor" {
  name = var.openstack_flavor
}

data "openstack_compute_keypair_v2" "xrootd_keypair" {
  name = "${var.environment}-xrootd"
}

# external IP

resource "openstack_compute_instance_v2" "xrootd_instance" {
  name      = "${var.environment}-xrootd"
  image_id  = data.openstack_images_image_v2.xrootd_image.id
  flavor_id = data.openstack_compute_flavor_v2.xrootd_flavor.flavor_id
  key_pair  = data.openstack_compute_keypair_v2.xrootd_keypair.name

  security_groups = ["default", "uksrc-ska-xrootd"]

  user_data = templatefile("cloud-config.yaml.tpl", {})

  network {
    name = "iris-ska-src-sriov"
  }
  network {
    name = "uksrc-ska-network"
  }
}
