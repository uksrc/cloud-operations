provider "harbor" {
  url      = var.harbor_dest_url
  username = var.primary_user
  password = var.primary_user_password
}

resource "harbor_label" "labels" {
  for_each = var.labels
  name     = each.key
  color    = each.value
}

resource "harbor_registry" "source" {
  name          = "remote-harbor"
  provider_name = "harbor"
  endpoint_url  = var.remote_harbor_url
}

resource "harbor_replication" "canfar" {
  for_each    = var.labels
  name        = "canfar-replication-${each.key}"
  action      = "pull"
  registry_id = harbor_registry.source.registry_id
  schedule    = "0 ${24 + index(local.label_keys, each.key)} 0 * * *"

  filters {
    labels = [each.key] # must be a label that already exists in Harbor
  }

  filters {
    resource = "image"
  }
}