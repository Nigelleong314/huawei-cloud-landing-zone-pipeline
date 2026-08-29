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

# Resolve the enterprise project (in the DNS account) by name. Blank => default ("0").
data "huaweicloud_enterprise_project" "dns" {
  count    = var.enterprise_project_name != "" ? 1 : 0
  provider = huaweicloud.dns
  name     = var.enterprise_project_name
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs
  network    = data.terraform_remote_state.network.outputs

  enterprise_project_id = var.enterprise_project_name != "" ? data.huaweicloud_enterprise_project.dns[0].id : "0"

  # VPC NAME → ID across hub + spokes. subnet key '<vpc>__<subnet>' → ID (hub only;
  # 05-network does not export spoke subnet IDs, so resolver endpoints must be in a
  # hub VPC).
  vpc_ids    = merge(try(local.network.hub_vpc_ids, {}), try(local.network.spoke_vpc_ids, {}))
  subnet_ids = try(local.network.hub_subnet_ids, {})
}

module "dns" {
  source    = "../../modules/dns"
  providers = { huaweicloud = huaweicloud.dns }

  enterprise_project_id = local.enterprise_project_id

  vpc_ids    = local.vpc_ids
  subnet_ids = local.subnet_ids

  public_zones       = var.public_zones
  private_zones      = var.private_zones
  recordsets         = var.recordsets
  resolver_endpoints = var.resolver_endpoints
  resolver_rules     = var.resolver_rules
  # 06-observability owns the query-log LTS group/stream (it converges and
  # archives them); this env only attaches the resolver access log to them.
  manage_query_log_infra = false
  access_logs            = var.access_logs
}
