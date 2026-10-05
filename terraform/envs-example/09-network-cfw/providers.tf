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
    key = "envs/09-network-cfw/terraform.tfstate"

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

# CFW rules deploy into var.cfw_account (the 05-network hub account that owns the
# firewall). assume_role BLOCK (temporary member AK/SK). NO default_tags by
# request: firewall rules stay untagged (safe — no cfw:* create action appears
# in the require_mandatory_tags SCP action list).
provider "huaweicloud" {
  alias  = "cfw"
  region = var.home_region

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.cfw_account
  }
}
