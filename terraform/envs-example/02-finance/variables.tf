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

# Cost-center EPs grouped by target account. The generated module calls in
# cost-centers.generated.tf index into this map per account.
variable "cost_centers_by_account" {
  type = map(map(object({
    description             = string
    enterprise_project_type = optional(string, "prod")
  })))
  default = {}
}
