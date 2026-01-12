terraform {
    required_providers {
        openstack = {
            source  = "terraform-provider-openstack/openstack"
            version = "~> 1.54"
        }
    }
}


resource "openstack_compute_instance_v2" "postgres_vm" {
    name      = ""
    image_id  = ""
}