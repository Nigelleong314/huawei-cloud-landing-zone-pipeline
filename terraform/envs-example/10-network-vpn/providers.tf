terraform {
  required_version = ">= 1.6.3"
  required_providers {
    huaweicloud = { source = "huaweicloud/huaweicloud", version = "~> 1.87" }
  }

  backend "s3" {
    key = "envs/10-network-vpn/terraform.tfstate"

    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

provider "huaweicloud" {
  region = var.home_region
}

# VPN deploys into var.vpn_account (the hub account). assume_role BLOCK (temporary
# member AK/SK); default_tags so taggable VPN resources carry the mandatory tags the
# require_mandatory_tags SCP expects. Un-merged from 05-network 2026-07 (was
# generated there as vpn.generated.tf); the alias stays "vpn" so the module call
# and the migrated state addresses are unchanged.
provider "huaweicloud" {
  alias  = "vpn"
  region = var.home_region

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.vpn_account
  }

  default_tags = var.default_tags
}
