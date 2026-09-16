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

variable "openstack_ska_uksrc_network" {
  description = "Main network to attach the XRootD instance to"
  type        = string
}

variable "openstack_ska_uksrc_subnet" {
  description = "Main subnet to attach the XRootD instance to"
  type        = string
}

variable "state_s3_endpoint" {
  description = "The S3 endpoint URL for the tofu state"
  type        = string
}

variable "default_username" {
  description = "The default username to use for the XRootD instance"
  type        = string
}

variable "openstack_wcdc_dirac_network" {
  description = "100Gbps network to attach the XRootD instance to"
  type        = string
}

variable "openstack_iris_network" {
  description = "IRIS network to attach the XRootD instance to"
  type        = string
}
