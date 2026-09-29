variable "home_region" {
  type    = string
  default = "ap-southeast-3"
}

variable "state_bucket_name" {
  type        = string
  description = "Globally-unique name for the OBS bucket holding Terraform state. e.g. mycorp-lz-tfstate"
}
