data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket                      = var.foundation_state_bucket
    key                         = var.foundation_state_key
    region                      = var.home_region
    endpoints                   = { s3 = "https://obs.${var.home_region}.myhuaweicloud.com" }
    access_key                  = var.master_access_key
    secret_key                  = var.master_secret_key
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs

  # SCP attach point: explicit override > a "Workloads" OU if the foundation
  # exposes one > the org root. Some organizations use BU-named OUs (no "Workloads" OU);
  # so it falls back to root. try() also guards foundations whose state predates
  # the workloads_ou_id output.
  attach_target = var.attach_target_id != "" ? var.attach_target_id : coalesce(try(local.foundation.workloads_ou_id, null), local.foundation.root_id)
}

# Org-level SCP guardrails. The per-account predefined-tag fan-out lives in the
# generated tagging.generated.tf (enable_scps = false there).
module "perimeter" {
  source = "../../modules/perimeter"

  environment = var.environment

  enable_scps      = true
  attach_target_id = local.attach_target
  org_id           = local.foundation.organization_id
  root_ou_id       = local.foundation.root_id

  scps = var.scps
}
