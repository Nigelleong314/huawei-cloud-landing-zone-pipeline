variable "home_region" { type = string }
variable "master_access_key" {
  type      = string
  sensitive = true
}
variable "master_secret_key" {
  type      = string
  sensitive = true
}
variable "default_tags" {
  type    = map(string)
  default = {}
}

variable "foundation_state_bucket" { type = string }
variable "foundation_state_key" {
  type    = string
  default = "envs/01-foundation/terraform.tfstate"
}

variable "network_state_bucket" { type = string }
variable "network_state_key" {
  type    = string
  default = "envs/05-network/terraform.tfstate"
}

variable "vpn_account" {
  type        = string
  default     = "lz-infra"
  description = "Account name (must match M1) the VPN resources deploy into (usually the hub account)."
}

variable "enterprise_project_name" {
  type        = string
  default     = ""
  description = "Landing-zone enterprise project name (from 02_Finance CostCenters); blank = default project."
}

# VPN config (from sheet 10_VPN; the module enforces the object shapes). The
# module.vpn call is generated into vpn.generated.tf.
variable "gateways" {
  type    = any
  default = []
}
variable "customer_gateways" {
  type    = any
  default = []
}
variable "connections" {
  # NOT marked sensitive: the module needs connection names as for_each keys, and a
  # sensitive value can't drive for_each. The PSK is marked sensitive inside the module
  # (psk = sensitive(...)) so it's still redacted in plan; tfvars.json is gitignored.
  type    = any
  default = []
}
