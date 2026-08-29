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

# ── Module 6 inputs (central audit, in the CTS-admin account) ──────────────

# Required, globally-unique OBS bucket names + KMS aliases (no defaults).
# These accept the {account-name} token (substituted in the module).
variable "audit_bucket_name" { type = string }
variable "kms_audit_alias" { type = string }
variable "audit_bucket_force_destroy" {
  type    = bool
  default = false
}
variable "cts_log_group_name" {
  type    = string
  default = "lz-cts"
}
variable "cts_log_stream_name" {
  type    = string
  default = ""
}
variable "audit_retention_days" {
  type    = number
  default = 365
}
variable "lts_hot_retention_days" {
  type    = number
  default = 90
}
variable "kms_pending_days" {
  type    = number
  default = 7
}

# ── Module 12 inputs (org LTS log aggregation, in the LTS-admin account) ───
# The converge fan-out (source lookups + module call) is GENERATED into
# logconverge.generated.tf from the LogConverge table.

variable "enable_log_aggregation" {
  type    = bool
  default = false
}
variable "archive_bucket_name" {
  type    = string
  default = ""
}
variable "kms_archive_alias" {
  type    = string
  default = ""
}
variable "archive_retention_days" {
  type    = number
  default = 365
}
variable "converged_retention_days" {
  type    = number
  default = 90
}
variable "transfer_period" {
  type    = number
  default = 30
}
variable "transfer_period_unit" {
  type    = string
  default = "min"
}
variable "archive_bucket_force_destroy" {
  type    = bool
  default = false
}

# ── Module 7 inputs (per-account ops) ──────────────────────────────────────

variable "topic_name" {
  type    = string
  default = "{account-name}-lz-alerts"
}

variable "subscribers" {
  type = list(object({
    protocol = string
    endpoint = string
  }))
  default = []
}

variable "one_click_alarms" {
  type = list(object({
    namespace     = string
    event_enabled = optional(bool, true)
  }))
  default = []
}

variable "audit_cold_after_days" {
  type        = number
  default     = 0
  description = "Days before CTS audit bucket objects move to COLD storage (0 = never)."
}

variable "archive_cold_after_days" {
  type        = number
  default     = 0
  description = "Days before log archive bucket objects move to COLD storage (0 = never)."
}
