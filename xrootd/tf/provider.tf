terraform {
  required_version = ">= 1.10.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0.0"
    }
  }

  backend "s3" {
    endpoint                    = "object.arcus.openstack.hpc.cam.ac.uk"
    bucket                      = "${var.environment}-tfstate"
    key                         = "environment.tfstate"
    region                      = "dummy"
    skip_region_validation      = true
    skip_credentials_validation = true
    use_path_style              = true
    use_lockfile                = true
  }
}
