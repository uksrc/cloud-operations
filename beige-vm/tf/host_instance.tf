variable "primary_user_ssh_key" {
  description = "Set in host_user.auto.tfvars"
  type        = string
}

variable "floating_ip" {
  description = "Set in network.auto.tfvars"
  type        = string
}

variable "fixed_ip" {
  description = "Set in network.auto.tfvars"
  type        = string
}

module "vm" {
  source = "../../common/tf/modules/vm"

  primary_user_ssh_key = var.primary_user_ssh_key
  floating_ip          = var.floating_ip
  fixed_ip             = var.fixed_ip

}
