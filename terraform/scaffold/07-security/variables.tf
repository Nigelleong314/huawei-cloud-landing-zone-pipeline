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
variable "observability_state_bucket" { type = string }
variable "observability_state_key" {
  type    = string
  default = "envs/06-observability/terraform.tfstate"
}
variable "network_state_bucket" { type = string }
variable "network_state_key" {
  type    = string
  default = "envs/05-network/terraform.tfstate"
}

variable "security_account" {
  type        = string
  default     = "lz-security"
  description = "Account name (must match M1) the SecMaster workspace deploys into."
}
variable "hub_account" {
  type        = string
  default     = "lz-infra"
  description = "Account name (must match M1) owning the hub network — edge protection (Anti-DDoS/WAF) deploys there."
}

variable "enable_secmaster" {
  type    = bool
  default = true
}
variable "secmaster_workspace_name" {
  type    = string
  default = "lz-secmaster"
}
variable "secmaster_modules" {
  type    = list(string)
  default = ["security_governance", "alert_management"]
}
variable "alert_rules" {
  type    = any
  default = []
}

variable "enable_hss" {
  type    = bool
  default = false
}
variable "enable_dbss" {
  type    = bool
  default = false
}

variable "enable_member_workspaces" {
  type    = bool
  default = false
}
variable "member_workspace_bindings" {
  type    = any
  default = []
}

# ── Edge protection (module 13, hub account) ────────────────────────────────

variable "antiddos" {
  # Rows from the 07_Security AntiDDoS table: { name, eip, threshold_mbps, alarm_topic }.
  type    = any
  default = []
}
variable "enable_waf" {
  type    = bool
  default = false
}
variable "waf_instance_name" {
  type    = string
  default = "lz-waf"
}
variable "waf_specification_code" {
  type    = string
  default = "waf.instance.professional"
}
variable "waf_availability_zone" {
  type    = string
  default = ""
}
variable "waf_vpc" {
  type        = string
  default     = ""
  description = "05_Network HubVPCs name hosting the WAF instance (the DMZ VPC)."
}
variable "waf_subnet" {
  type        = string
  default     = ""
  description = "05_Network HubSubnets name (within waf_vpc) for the WAF instance."
}
variable "waf_policy_name" {
  type    = string
  default = "lz-waf-policy"
}
variable "waf_domains" {
  # Rows from the 07_Security WAFDomains table.
  type    = any
  default = []
}
