variable "primary_user" {
  description = "Username for the primary harbor user"
  type        = string
}

variable "primary_user_password" {
  description = "Password for the primary harbor user"
  type        = string
  sensitive   = true
}

variable "harbor_dest_url" {
  description = "Destinitaion harbor url where replication is configured"
  type        = string
}

variable "remote_harbor_url" {
  description = "Remote harbor url from where artifacts are synced"
  type        = string
}

variable "labels" {
  description = "Map of Harbor label names to their hex color codes"
  type        = map(string)
  default = {
    desktop     = "#0095D3"
    notebook    = "#48960C"
    carta       = "#F52F52"
    contributed = "#FFDC0B"
    firefly     = "#FF5501"
  }
}