variable "home_region" {
  type        = string
  description = "Primary deployment region"
}

variable "default_tags" {
  type    = map(string)
  default = {}
}
variable "master_default_tags" {
  type    = map(string)
  default = {}
}

variable "master_access_key" {
  type        = string
  sensitive   = true
  description = "Master-account AK"
}

variable "master_secret_key" {
  type        = string
  sensitive   = true
  description = "Master-account SK"
}

variable "environment" {
  type    = string
  default = "shared"
}

# ── Remote state location for module 1 foundation outputs ──────────────────

variable "foundation_state_bucket" {
  type        = string
  description = "OBS bucket holding the 01-foundation tfstate"
}

variable "foundation_state_key" {
  type        = string
  default     = "envs/01-foundation/terraform.tfstate"
  description = "Key path in the state bucket for the 01-foundation state"
}

# ── Module 2 passthroughs ──────────────────────────────────────────────────

variable "groups" {
  type    = any
  default = null
}
variable "users" {
  type    = any
  default = null
}
variable "permission_sets" {
  type    = any
  default = null
}
variable "account_assignments" {
  type        = list(object({ account_id = string, group_name = string, permission_set = string }))
  default     = []
  description = "IC account assignments (group -> permission set per account). Empty = no assignments."
}
variable "registered_regions" {
  type    = list(string)
  default = []
}
variable "service_agencies" {
  type    = any
  default = null
}

# IC instance-wide policies + permission-set session default (-> ic_content).
# Policy objects default to {} so the module's per-key defaults apply when unset.
variable "session_duration" {
  type    = string
  default = "PT8H"
}
variable "ic_password_policy" {
  type    = any
  default = {}
}
variable "ic_mfa_management" {
  type    = any
  default = {}
}

# Per-account IAM login policy (-> generated iam_baseline calls).
variable "iam_login_policy" {
  type    = any
  default = {}
}
