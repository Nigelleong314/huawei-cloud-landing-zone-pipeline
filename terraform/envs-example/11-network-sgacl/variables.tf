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

# ── Module 15 inputs (workload security groups) ─────────────────────────────

# account name -> its groups + rules (11_SGACL SecurityGroups / SGRules rows).
# The generated sgacl.generated.tf passes each account's slice to one module call.
variable "secgroups" {
  type = map(object({
    groups = list(object({
      name        = string
      description = optional(string, "")
      tags        = optional(map(string), {})
    }))
    rules = list(object({
      sg          = string
      direction   = string
      protocol    = optional(string, "any")
      ports       = optional(string, "")
      remote      = string
      action      = optional(string, "allow")
      description = optional(string, "")
    }))
  }))
  default = {}
}
