locals {
  primary_user = var.primary_user

  ansible_base_command = <<-EOT
    cd ${path.module}/../ansible
        set -a
    [ -f .env ] && source .env
    set +a
    NETWORK_CIDR='${var.network_cidr}' ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
      -i '${openstack_compute_instance_v2.mango_vm.access_ip_v4},' \
      -u ${local.primary_user} \
    EOT

  system_update_command       = "sleep 60\n${local.ansible_base_command} update_system.yml"
  manage_users_command        = "${local.ansible_base_command} manage_users.yml"
  add_opkssh_command          = "${local.ansible_base_command} add_opkssh.yml"

}

resource "null_resource" "system_update_provisioner" {
  depends_on = [openstack_compute_instance_v2.mango_vm]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.mango_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/update_system.yml")
    role_hash        = md5(join("", [for f in fileset("${path.module}/../../common/ansible/roles/update_system", "**") : filemd5("${path.module}/../../common/ansible/roles/update_system/${f}")]))
    vars_hash = md5(join("", [
      filemd5("${path.module}/../ansible/group_vars/all/system.yml"),
      try(filemd5("${path.module}/../ansible/.env"), "")
    ]))
    provisioner_command_hash = md5(local.system_update_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.system_update_command
  }
}

resource "null_resource" "manage_users_provisioner" {
  depends_on = [null_resource.system_update_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.mango_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/manage_users.yml")
    role_hash        = md5(join("", [for f in fileset("${path.module}/../../common/ansible/roles/manage_users", "**") : filemd5("${path.module}/../../common/ansible/roles/manage_users/${f}")]))
    vars_hash = md5(join("", [
      try(filemd5("${path.module}/../ansible/group_vars/all/users.yml"), "")
    ]))
    provisioner_command_hash = md5(local.manage_users_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.manage_users_command
  }
}

resource "null_resource" "add_opkssh_provisioner" {
  depends_on = [null_resource.manage_users_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.mango_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/add_opkssh.yml")
    role_hash        = md5(join("", [for f in fileset("${path.module}/../../common/ansible/roles/add_opkssh", "**") : filemd5("${path.module}/../../common/ansible/roles/add_opkssh/${f}")]))
    vars_hash = md5(join("", [
      try(filemd5("${path.module}/../ansible/group_vars/all/users.yml"), "")
    ]))
    provisioner_command_hash = md5(local.add_opkssh_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.add_opkssh_command
  }
}
