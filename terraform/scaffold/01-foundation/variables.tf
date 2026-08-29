# Env-level variables. Most pass through to module 1 unchanged.

variable "home_region" {
  type        = string
  description = "Primary deployment region (Huawei region ID, e.g. ap-southeast-3, cn-east-3, cn-north-4)."
  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-?[0-9]+$", var.home_region))
    error_message = "home_region must be a Huawei region ID like ap-southeast-3 or cn-east-3."
  }
}

variable "default_tags" {
  type    = map(string)
  default = {}
}

variable "master_access_key" {
  type        = string
  description = "Huawei Cloud master-account AK"
  sensitive   = true
}

variable "master_secret_key" {
  type        = string
  description = "Huawei Cloud master-account SK"
  sensitive   = true
}

variable "environment" {
  type        = string
  description = "Environment label applied to default_tags"
  default     = "shared"
}

# ── Module 1 passthroughs ──────────────────────────────────────────────────

variable "enabled_policy_types" {
  type        = set(string)
  description = "Policy types enabled at org root. Default: SCP + tag policy."
  default     = ["service_control_policy", "tag_policy"]
}

variable "organizational_units" {
  type        = map(object({}))
  description = "OUs to create directly under root (flat Day-1)."
  default = {
    Workloads = {}
  }
}

variable "core_accounts" {
  type = map(object({
    email       = string
    ou          = optional(string, "")
    description = optional(string, "")
  }))
  description = "Core accounts (logging/security/network/ops, etc.). See module 1 docs."
}

variable "workload_accounts" {
  type = map(object({
    email       = string
    ou          = optional(string, "")
    description = optional(string, "")
  }))
  description = "Workload accounts."
  default     = {}
}

variable "cross_account_agency_name" {
  type        = string
  description = "Cross-account agency name auto-created in every created account."
  default     = "OrganizationAccountAccessAgency"
}

variable "identity_center_alias" {
  type        = string
  description = "Optional alias for Identity Center instance."
  default     = ""
}

variable "trusted_services" {
  type        = list(string)
  description = "Organizations trusted services (service.<NAME> format)."
  default = [
    "service.CTS",
    "service.IdentityCenter",
    "service.RAM",
  ]
}

variable "delegated_administrators" {
  type        = map(string)
  description = "Map of trusted service → delegated-admin account name (from M1 TrustedServices.DelegatedAdmin)."
  default     = {}
}

variable "tag_policies" {
  type = list(object({
    name        = string
    description = string
    content     = string
  }))
  description = "Custom tag policies to attach at the root."
  default     = []
}

variable "create_enterprise_project" {
  type        = bool
  description = "Create the LZ bootstrap enterprise project."
  default     = false
}

variable "enterprise_project_name" {
  type        = string
  description = "Bootstrap enterprise project name."
  default     = "landing-zone"
}
