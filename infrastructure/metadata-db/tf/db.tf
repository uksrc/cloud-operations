resource "null_resource" "postgres_provisioner" {
  depends_on = [openstack_compute_instance_v2.postgres_vm]

  triggers = {
    instance_id = openstack_compute_instance_v2.postgres_vm.id
    # Re-run if playbook changes
    # playbook_hash = filemd5("${path.module}/ansible/postgres.yml")
  }

  provisioner "local-exec" {
    command = <<-EOT
            sleep 60
            cd ${path.module}/../ansible
            # ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
            #   -i '${openstack_compute_instance_v2.postgres_vm.access_ip_v4},' \
            #   -u ${local.primary_user} \
            #   postgres.yml
        EOT
  }
}
