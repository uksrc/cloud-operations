output "instance_id" {
  description = "Instance ID"
  value       = openstack_compute_instance_v2.xrootd_instance.id
}

output "instance_ip_addresses" {
  description = "IP address of the XRootD VM instance"
  value       = [for n in openstack_compute_instance_v2.xrootd_instance.network : n.fixed_ip_v4]
}
