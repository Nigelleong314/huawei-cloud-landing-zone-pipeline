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

variable "attach_target_id" {
  type        = string
  default     = ""
  description = "Entity to attach the SCPs to. Empty = a 'Workloads' OU if the foundation exposes one, else the org root."
}

# The 8 guardrail SCPs. Passthrough to module 04-perimeter, which owns the full
# typed schema + per-policy defaults. Each enabled policy is a block keyed by its
# policy name (deny_leave_org, deny_root_user, deny_unauthorized_ram_share,
# deny_unauthorized_rms_aggregation, require_mandatory_tags, deny_public_obs,
# protect_cts_tracker, deny_outside_allowed_region) carrying its own settings.
variable "scps" {
  type        = any
  default     = {}
  description = "Per-policy SCP config. See modules-v2/perimeter/variables.tf for the full schema."
}

# Predefined-tag dictionary applied per account (generated fan-out).
variable "predefined_tags" {
  type = list(object({
    key    = string
    values = optional(list(string), [])
  }))
  default = []
}

# Config (RMS) org setup. config_admin_account selects which account runs it;
# the generated config.generated.tf wires the module call to that account's
# provider alias. Empty account = no Config setup emitted.
variable "config_admin_account" {
  type        = string
  default     = ""
  description = "Account (M1 Name) to run org-wide Config on. Empty = skip Config setup."
}

variable "config" {
  type        = any
  default     = {}
  description = "Config (RMS) recorder + aggregator settings. See modules-v2/perimeter/variables.tf for the schema."
}

variable "conformance_packs" {
  type        = any
  default     = []
  description = "Org-wide Config conformance packs (name/enabled/template_key/excluded_accounts). See modules-v2/perimeter/variables.tf."
}
