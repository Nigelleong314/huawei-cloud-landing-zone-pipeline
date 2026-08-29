variable "home_region" { type = string }
variable "master_access_key" {
  type      = string
  sensitive = true
}
variable "master_secret_key" {
  type      = string
  sensitive = true
}
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

variable "cfw_account" {
  type        = string
  default     = "lz-infra"
  description = "Account name (must match M1) that owns the hub CFW (= 05_Network hub_account). The env assumes this account's OrganizationAccountAccessAgency."
}

variable "enterprise_project_name" {
  type        = string
  default     = ""
  description = "Enterprise project the hub CFW belongs to (= 05_Network enterprise_project_name). Resolved to an ID and passed to the attack-defense data source/rules, which are EP-scoped. Blank = default project '0'."
}

# ── CFW config (from sheet 09_CFW; the module enforces the object shapes) ──────
variable "address_groups" {
  type    = any
  default = []
}
variable "domain_groups" {
  type    = any
  default = []
}
variable "service_groups" {
  type    = any
  default = []
}
variable "acl_rules" {
  type    = any
  default = []
}
variable "black_white_lists" {
  type    = any
  default = []
}
# Attack defense on the internet protected object (module resources; the IPS
# mode/patching live on the firewall instance in 05-network).
variable "enable_anti_virus" {
  type    = bool
  default = false
}
variable "enable_reverse_shell_defense" {
  type    = bool
  default = false
}
variable "alarm_topic_name" {
  type    = string
  default = ""
}
variable "enable_attack_alarm" {
  type    = bool
  default = false
}
variable "enable_traffic_alarm" {
  type    = bool
  default = false
}
variable "enable_eip_unprotected_alarm" {
  type    = bool
  default = false
}
variable "enable_threat_intel_alarm" {
  type    = bool
  default = false
}
