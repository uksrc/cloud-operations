terraform {
  required_version = ">=1.0.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 1.54"
    }
  }

  backend "s3" {
   endpoint = "s3.echo.stfc.ac.uk"
   bucket = "tofu-state"
   key = "postgres-vm/postgres-vm.state"
   use_lockfile = true
   region = "RegionOne"
   skip_region_validation = true
   skip_credentials_validation = true
   skip_metadata_api_check = true
   skip_requesting_account_id = true
   use_path_style = true
 }
}
