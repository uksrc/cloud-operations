locals {
  ansible_base_command = <<-EOT
    cd ${path.module}/../ansible
        set -a
    [ -f .env ] && source .env
    set +a
    NETWORK_CIDR='${var.network_cidr}' ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
      -i '${openstack_compute_instance_v2.postgres_vm.access_ip_v4},' \
      -u ${local.primary_user} \
    EOT

  system_update_command       = "sleep 60\n${local.ansible_base_command} update_system.yml"
  postgres_install_command    = "${local.ansible_base_command} install_and_configure_postgres.yml"
  caomdb_schema_setup_command = "${local.ansible_base_command} setup_mm_db_schema.yml"
  sdsdb_schema_setup_command  = "${local.ansible_base_command} setup_sds_db_schema.yml"
}

resource "null_resource" "system_update_provisioner" {
  depends_on = [openstack_compute_instance_v2.postgres_vm]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.postgres_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/update_system.yml")
    role_hash        = md5(join("", [for f in fileset("${path.module}/../ansible/roles/update_system", "**") : filemd5("${path.module}/../ansible/roles/update_system/${f}")]))
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

resource "null_resource" "postgres_install_provisioner" {
  depends_on = [null_resource.system_update_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.postgres_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/install_and_configure_postgres.yml")
    role_hash        = md5(join("", [for f in fileset("${path.module}/../ansible/roles/install_postgresql", "**") : filemd5("${path.module}/../ansible/roles/install_postgresql/${f}")]))
    vars_hash = md5(join("", [
      filemd5("${path.module}/../ansible/group_vars/all/postgres.yml"),
      try(filemd5("${path.module}/../ansible/.env"), "")
    ]))
    provisioner_command_hash = md5(local.postgres_install_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.postgres_install_command
  }
}


// Schemas

resource "null_resource" "caomdb_schema_provisioner" {
  depends_on = [null_resource.postgres_install_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.postgres_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/setup_mm_db_schema.yml")
    vars_hash = md5(join("", [
      filemd5("${path.module}/../ansible/group_vars/all/schema/caomdb.yml"),
      filemd5("${path.module}/../ansible/group_vars/all/postgres.yml"),
      try(filemd5("${path.module}/../ansible/.env"), "")
    ]))
    role_hash                = md5(join("", [for f in fileset("${path.module}/../ansible/roles/setup_db_schema", "**") : filemd5("${path.module}/../ansible/roles/setup_db_schema/${f}")]))
    provisioner_command_hash = md5(local.caomdb_schema_setup_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.caomdb_schema_setup_command
  }
}

resource "null_resource" "sds_schema_provisioner" {
  depends_on = [null_resource.postgres_install_provisioner]

  triggers = {
    host_instance_id = openstack_compute_instance_v2.postgres_vm.id
    playbook_hash    = filemd5("${path.module}/../ansible/setup_sds_db_schema.yml")
    vars_hash = md5(join("", [
      filemd5("${path.module}/../ansible/group_vars/all/schema/sdsdb.yml"),
      filemd5("${path.module}/../ansible/group_vars/all/postgres.yml"),
      try(filemd5("${path.module}/../ansible/.env"), "")
    ]))
    role_hash                = md5(join("", [for f in fileset("${path.module}/../ansible/roles/setup_db_schema", "**") : filemd5("${path.module}/../ansible/roles/setup_db_schema/${f}")]))
    provisioner_command_hash = md5(local.sdsdb_schema_setup_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.sdsdb_schema_setup_command
  }
}
