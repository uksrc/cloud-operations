locals {
  ansible_command = <<-EOT
		sleep 60
    cd ${path.module}/../ansible
		set -a
    [ -f .env ] && source .env
    set +a
    ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
      -i '${openstack_compute_instance_v2.postgres_vm.access_ip_v4},' \
      -u ${local.primary_user} \
      postgres.yml
	EOT
}

resource "null_resource" "postgres_provisioner" {
  depends_on = [openstack_compute_instance_v2.postgres_vm]

  triggers = {
    instance_id = openstack_compute_instance_v2.postgres_vm.id
    # Re-run if playbook changes
    playbook_hash = filemd5("${path.module}/../ansible/postgres.yml")
    # Re-run if roles directory changes
    roles_hash = md5(join("", [for f in fileset("${path.module}/../ansible/roles", "**") : filemd5("${path.module}/../ansible/roles/${f}")]))
    # Re-run if group_vars directory changes
    group_vars_hash = md5(join("", [for f in fileset("${path.module}/../ansible/group_vars", "**") : filemd5("${path.module}/../ansible/group_vars/${f}")]))
    # Re-run if provisioner command changes
    provisioner_command = md5(local.ansible_command)
  }

  provisioner "local-exec" {
		interpreter = ["/bin/bash", "-c"]
    command = local.ansible_command
  }
}
