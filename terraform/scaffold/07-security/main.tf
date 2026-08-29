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

data "terraform_remote_state" "observability" {
  backend = "s3"
  config = {
    bucket                      = var.observability_state_bucket
    key                         = var.observability_state_key
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

locals {
  foundation    = data.terraform_remote_state.foundation.outputs
  observability = data.terraform_remote_state.observability.outputs
  network       = data.terraform_remote_state.network.outputs

  # Wire SecMaster cloud_log_resources to LTS groups from module 6
  cloud_log_resources = [
    for group_name, group_id in lookup(local.observability, "lts_group_ids", {}) : {
      name         = group_name
      type         = "LTS"
      log_group_id = group_id
    }
  ]
}

# Warn (not fail) when SecMaster deploys without LTS log wiring: the
# lts_group_ids output only exists once 06-observability has been applied.
check "observability_log_wiring" {
  assert {
    condition     = length(local.cloud_log_resources) > 0
    error_message = "SecMaster log wiring is empty: 06-observability's lts_group_ids output is absent (apply or refresh 06), so SecMaster would deploy without LTS log sources."
  }
}

module "security" {
  source    = "../../modules/security"
  providers = { huaweicloud = huaweicloud.lz_security }

  environment              = var.environment
  enable_secmaster         = var.enable_secmaster
  secmaster_workspace_name = var.secmaster_workspace_name
  secmaster_project_name   = var.home_region
  secmaster_modules        = var.secmaster_modules
  cloud_log_resources      = local.cloud_log_resources
  alert_rules              = var.alert_rules

  enable_hss  = var.enable_hss
  enable_dbss = var.enable_dbss

  enable_member_workspaces  = var.enable_member_workspaces
  member_workspace_bindings = var.member_workspace_bindings
}

# ── Edge protection (module 13): Basic Anti-DDoS on hub EIPs + dedicated WAF ─
# Runs in the HUB account (huaweicloud.hub). Name -> ID resolution comes from the
# 05-network state: EIPs by name, the WAF VPC/subnet by 05_Network names.

module "edge_protection" {
  source    = "../../modules/edge-protection"
  providers = { huaweicloud = huaweicloud.hub }

  eip_ids  = try(local.network.eip_ids, {})
  antiddos = var.antiddos

  enable_waf             = var.enable_waf
  waf_instance_name      = var.waf_instance_name
  waf_specification_code = var.waf_specification_code
  waf_availability_zone  = var.waf_availability_zone
  waf_vpc_id             = var.waf_vpc != "" ? try(local.network.hub_vpc_ids[var.waf_vpc], "") : ""
  waf_subnet_id          = var.waf_vpc != "" && var.waf_subnet != "" ? try(local.network.hub_subnet_ids["${var.waf_vpc}__${var.waf_subnet}"], "") : ""
  waf_policy_name        = var.waf_policy_name
  waf_domains            = var.waf_domains
}
