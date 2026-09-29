# --- DNS inputs ---

variable "home_region" { type = string }
variable "environment" {
  type    = string
  default = "shared"
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

variable "dns_account" {
  type        = string
  default     = "lz-infra"
  description = "Account name (must match 01-foundation) the DNS resources deploy into. The env assumes this account's OrganizationAccountAccessAgency."
}

variable "enterprise_project_name" {
  type        = string
  default     = ""
  description = "Enterprise project (in dns_account) for the DNS zones. Blank = default project."
}

# ── DNS config (the module enforces the object shapes) ──────
variable "public_zones" {
  type    = any
  default = []
}
variable "private_zones" {
  type    = any
  default = []
}
variable "recordsets" {
  type    = any
  default = []
}
variable "resolver_endpoints" {
  type    = any
  default = []
}
variable "resolver_rules" {
  type    = any
  default = []
}
variable "access_logs" {
  type    = any
  default = []
}
