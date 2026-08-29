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

data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket                      = var.network_state_bucket
    key                         = var.network_state_key
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

# Enterprise project the VPN resources are assigned to (same landing-zone EP
# as the hub; blank name = the default project "0").
data "huaweicloud_enterprise_project" "lz" {
  count    = var.enterprise_project_name != "" ? 1 : 0
  provider = huaweicloud.vpn
  name     = var.enterprise_project_name
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs
  network    = data.terraform_remote_state.network.outputs

  enterprise_project_id = var.enterprise_project_name != "" ? data.huaweicloud_enterprise_project.lz[0].id : "0"
}
