# --- Provider requirements and configuration ---

terraform {
  required_version = ">= 1.6.3"
  required_providers {
    huaweicloud = { source = "huaweicloud/huaweicloud", version = "~> 1.87" }
  }

  backend "s3" {
    bucket = "example-lz-obs-tfstate-01"
    region = "ap-southeast-1"
    endpoints = {
      s3 = "https://obs.ap-southeast-1.myhuaweicloud.com"
    }
    # key is the HISTORICAL (pre-renumber) env name - it pins the live OBS state; never change
    key                         = "envs/07-security/terraform.tfstate"
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

provider "huaweicloud" {
  region = var.home_region

  default_tags = var.default_tags
}

provider "huaweicloud" {
  alias              = "lz_security"
  region             = var.home_region
  domain_name        = local.foundation.master_account_name
  agency_name        = local.foundation.cross_account_agency_name
  default_tags       = var.default_tags
  agency_domain_name = var.security_account
}

# Edge protection deploys into the 05-network HUB account: the
# Anti-DDoS EIPs and the WAF VPC live there. assume_role block (temporary member
# AK/SK) like 05-network's vpn provider; default_tags so the require_mandatory_tags SCP allows creates.
provider "huaweicloud" {
  alias  = "hub"
  region = var.home_region

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.hub_account
  }

  default_tags = var.default_tags
}
