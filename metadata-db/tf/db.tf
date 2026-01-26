locals {
  ansible_base_command = <<-EOT
    cd ${path.module}/../ansible
		set -a
    [ -f .env ] && source .env
    set +a
    ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
      -i '${openstack_compute_instance_v2.postgres_vm.access_ip_v4},' \
      -u ${local.primary_user} \
	EOT

  system_update_command       = "sleep 60\n${local.ansible_base_command} update_system.yml"
  postgres_install_command    = "${local.ansible_base_command} install_and_configure_postgres.yml"
  caomdb_schema_setup_command = "${local.ansible_base_command} setup_metadata_db_schema.yml"
}

resource "null_resource" "system_update_provisioner" {
  depends_on = [openstack_compute_instance_v2.postgres_vm]

  triggers = {
    instance_id = openstack_compute_instance_v2.postgres_vm.id
    # Re-run if update_system playbook changes
    playbook_hash = filemd5("${path.module}/../ansible/update_system.yml")
    # Re-run if update_system role changes
    update_system_role_hash = md5(join("", [for f in fileset("${path.module}/../ansible/roles/update_system", "**") : filemd5("${path.module}/../ansible/roles/update_system/${f}")]))
    # Re-run if group_vars directory changes
    system_vars_hash = filemd5("${path.module}/../ansible/group_vars/all/system.yml")
    # Re-run if provisioner command changes
    provisioner_command = md5(local.system_update_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.system_update_command
  }
}

resource "null_resource" "postgres_install_provisioner" {
  depends_on = [null_resource.system_update_provisioner]

  triggers = {
    instance_id = openstack_compute_instance_v2.postgres_vm.id
    # Re-run if install_postgres playbook changes
    playbook_hash = filemd5("${path.module}/../ansible/install_and_configure_postgres.yml")
    # Re-run if infrastructure roles change
    install_postgresql_hash = md5(join("", [for f in fileset("${path.module}/../ansible/roles/install_postgresql", "**") : filemd5("${path.module}/../ansible/roles/install_postgresql/${f}")]))
    configure_database_hash = md5(join("", [for f in fileset("${path.module}/../ansible/roles/configure_database", "**") : filemd5("${path.module}/../ansible/roles/configure_database/${f}")]))
    # Re-run if postgres variables changes
    postgres_vars_hash = filemd5("${path.module}/../ansible/group_vars/all/postgres.yml")
    # Re-run if provisioner command changes
    provisioner_command = md5(local.postgres_install_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.postgres_install_command
  }
}

resource "null_resource" "caomdb_schema_provisioner" {
  depends_on = [null_resource.postgres_install_provisioner]

  triggers = {
    instance_id = openstack_compute_instance_v2.postgres_vm.id
    # Re-run if postgres playbook (schema setup) changes
    playbook_hash = filemd5("${path.module}/../ansible/setup_metadata_db_schema.yml")
    # Re-run if caomdb or postgres variables change
    caomdb_vars_hash = filemd5("${path.module}/../ansible/group_vars/all/schema/caomdb.yml")
    postgres_vars_hash = filemd5("${path.module}/../ansible/group_vars/all/postgres.yml")
    # Re-run if setup_metadata_schema role changes
    schema_role_hash = md5(join("", [for f in fileset("${path.module}/../ansible/roles/setup_metadata_db_schema", "**") : filemd5("${path.module}/../ansible/roles/setup_metadata_db_schema/${f}")]))
    # Re-run if provisioner command changes
    provisioner_command = md5(local.caomdb_schema_setup_command)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = local.caomdb_schema_setup_command
  }
}
