# --- Observability configuration ---

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

  member_account_ids = [for k, v in local.foundation.accounts : v.id]
}

# The central audit module (CTS-admin account) and the per-account ops modules
# live in providers.generated.tf and observability.generated.tf
# (one audit call and one ops call per account). Do not add module
# calls here.
