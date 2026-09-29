# --- Foundation state ---

# Cost-center enterprise projects, fanned out per target account.
# The module calls and cross-account provider aliases live in
# cost-centers.generated.tf and providers.generated.tf
# (one per target account). This file
# only wires the foundation remote state those generated aliases depend on.

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
