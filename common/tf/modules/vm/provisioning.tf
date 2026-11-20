variable "additional_dependencies" {
  description = "Does this VM require additional dependencies?"
  type        = bool
  default     = false
}

variable "ansible_dir" {
  description = "Directory containing the caller's Ansible configuration and optional dependency playbook; defaults to ../ansible relative to the root module"
  type        = string
  default     = null
}

locals {
  ansible_dir        = abspath(var.ansible_dir != null ? var.ansible_dir : "${path.root}/../ansible")
  module_ansible_dir = abspath("${path.module}/ansible")
  common_roles_dir   = abspath("${path.module}/../../../ansible/roles")

  ansible_environment = {
    VM_ANSIBLE_DIR        = local.ansible_dir
    VM_MODULE_ANSIBLE_DIR = local.module_ansible_dir
    VM_COMMON_ROLES_DIR   = local.common_roles_dir
    VM_NETWORK_CIDR       = var.network_cidr
    VM_PRIMARY_USER       = var.primary_user
    VM_HOST_IP            = openstack_compute_instance_v2.vm.access_ip_v4
  }

  ansible_base_command = <<-EOT
    set -a
    [ -f .env ] && source .env
    set +a
    export ANSIBLE_ROLES_PATH="$VM_COMMON_ROLES_DIR:$VM_ANSIBLE_DIR/roles$${ANSIBLE_ROLES_PATH:+:$ANSIBLE_ROLES_PATH}"
    NETWORK_CIDR="$VM_NETWORK_CIDR" ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
      -i "$VM_HOST_IP," \
      -u "$VM_PRIMARY_USER" \
    EOT

  system_update_command = "sleep 60\n${local.ansible_base_command} \"$VM_MODULE_ANSIBLE_DIR/update_system.yml\""
  manage_users_command  = "${local.ansible_base_command} \"$VM_MODULE_ANSIBLE_DIR/manage_users.yml\""
  dependencies_command  = "${local.ansible_base_command} dependencies.yml"
  add_opkssh_command    = "${local.ansible_base_command} \"$VM_MODULE_ANSIBLE_DIR/add_opkssh.yml\""
}

resource "null_resource" "system_update_provisioner" {
  depends_on = [openstack_compute_instance_v2.vm]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.vm.id
    playbook_hash    = filemd5("${local.module_ansible_dir}/update_system.yml")
    role_hash        = md5(join("", [for f in fileset("${local.common_roles_dir}/update_system", "**") : filemd5("${local.common_roles_dir}/update_system/${f}")]))
    vars_hash = md5(join("", [
      filemd5("${local.ansible_dir}/group_vars/all/system.yml"),
      try(filemd5("${local.ansible_dir}/.env"), "")
    ]))
    provisioner_command_hash = md5("${local.system_update_command}${jsonencode(local.ansible_environment)}")
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    working_dir = local.ansible_dir
    environment = local.ansible_environment
    command     = local.system_update_command
  }
}

resource "null_resource" "dependencies_provisioner" {
  depends_on = [null_resource.system_update_provisioner]
  count      = var.additional_dependencies ? 1 : 0

  triggers = {
    host_instance_id = openstack_compute_instance_v2.vm.id
    playbook_hash    = filemd5("${local.ansible_dir}/dependencies.yml")
    role_hash        = md5(join("", [for f in fileset("${local.ansible_dir}/roles", "**") : filemd5("${local.ansible_dir}/roles/${f}")]))

    provisioner_command_hash = md5("${local.dependencies_command}${jsonencode(local.ansible_environment)}")
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    working_dir = local.ansible_dir
    environment = local.ansible_environment
    command     = local.dependencies_command
  }
}

resource "null_resource" "manage_users_provisioner" {
  depends_on = [null_resource.dependencies_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.vm.id
    playbook_hash    = filemd5("${local.module_ansible_dir}/manage_users.yml")
    role_hash        = md5(join("", [for f in fileset("${local.common_roles_dir}/manage_users", "**") : filemd5("${local.common_roles_dir}/manage_users/${f}")]))
    vars_hash = md5(join("", [
      filemd5("${local.ansible_dir}/group_vars/all/users.yml")
    ]))
    provisioner_command_hash = md5("${local.manage_users_command}${jsonencode(local.ansible_environment)}")
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    working_dir = local.ansible_dir
    environment = local.ansible_environment
    command     = local.manage_users_command
  }
}

resource "null_resource" "add_opkssh_provisioner" {
  depends_on = [null_resource.manage_users_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.vm.id
    playbook_hash    = filemd5("${local.module_ansible_dir}/add_opkssh.yml")
    role_hash        = md5(join("", [for f in fileset("${local.common_roles_dir}/add_opkssh", "**") : filemd5("${local.common_roles_dir}/add_opkssh/${f}")]))
    vars_hash = md5(join("", [
      filemd5("${local.ansible_dir}/group_vars/all/users.yml")
    ]))
    provisioner_command_hash = md5("${local.add_opkssh_command}${jsonencode(local.ansible_environment)}")
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    working_dir = local.ansible_dir
    environment = local.ansible_environment
    command     = local.add_opkssh_command
  }
}
