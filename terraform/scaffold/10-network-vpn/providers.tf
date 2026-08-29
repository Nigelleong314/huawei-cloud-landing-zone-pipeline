provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key
}

# VPN deploys into var.vpn_account (the hub account). assume_role BLOCK (temporary
# member AK/SK); default_tags so taggable VPN resources carry the mandatory tags the
# require_mandatory_tags SCP expects. Un-merged from 05-network 2026-07 (was
# generated there as vpn.generated.tf); the alias stays "vpn" so the module call
# and the migrated state addresses are unchanged.
provider "huaweicloud" {
  alias      = "vpn"
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.vpn_account
  }

  default_tags = var.default_tags
}
