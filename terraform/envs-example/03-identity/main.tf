# --- Identity configuration ---

# 03-identity
# IC content (1 call to the identity module in master) +
# IAM baseline per-account (1 call per created account, via provider alias).
# Add/remove accounts by:
#   1. Adding a provider alias in providers.tf
#   2. Adding a module "iam_baseline_<alias>" block below
# Pattern C: provider aliases are explicit, not generated dynamically (Terraform
# does not support for_each over module providers).

# ── Read foundation outputs from remote state ────────────────────────────────

data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket                      = var.foundation_state_bucket
    key                         = var.foundation_state_key
    region                      = var.home_region
    endpoints                   = { s3 = "https://obs.${var.home_region}.myhuaweicloud.com" }
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs
}

# ── IC content (master account, default provider) ─────────────────────────

module "ic_content" {
  source = "../../modules/identity"

  environment                    = var.environment
  enable_identity_center_content = true
  enable_iam_baseline            = false

  identity_store_id           = local.foundation.identity_store_id
  identity_center_instance_id = local.foundation.identity_center_instance_id

  # Pass var if user overrides; else the identity module defaults apply.
  groups              = var.groups != null ? var.groups : null
  users               = var.users != null ? var.users : null
  permission_sets     = var.permission_sets != null ? var.permission_sets : null
  account_assignments = var.account_assignments # empty = no assignments
  registered_regions  = var.registered_regions

  session_duration   = var.session_duration
  ic_password_policy = var.ic_password_policy
  ic_mfa_management  = var.ic_mfa_management
}

# ── IAM baseline (per-account) ─────────────────────────────────────────────
# Per-account fan-out lives in:
#   providers.generated.tf    (one alias per account)
#   iam-baseline.generated.tf (master + one module call per account)
# To add or remove an account, copy or delete the matching blocks in both.
