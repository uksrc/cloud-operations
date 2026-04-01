variable "environment" {
  description = "The UKSRC node name e.g. cam-dev"
  type        = string
}

variable "openstack_image" {
  description = "Name of the OpenStack image to use for the XRootD instance"
  type        = string
}

variable "openstack_flavor" {
  description = "Name of the OpenStack flavor to use for the XRootD instance"
  type        = string
}
