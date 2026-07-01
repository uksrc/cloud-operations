terraform {
  required_version = ">=1.0.0"
  required_providers {
    harbor = {
      source  = "goharbor/harbor" # or flbla/harbor depending on which you use
      version = "~> 3.12.0"
    }
  }
}