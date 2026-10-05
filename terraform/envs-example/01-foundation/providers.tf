# --- Provider requirements and configuration ---

terraform {
  required_version = ">= 1.6.3"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = "~> 1.87"
    }
  }

  backend "s3" {
    bucket = "example-lz-obs-tfstate-01"
    region = "ap-southeast-1"
    endpoints = {
      s3 = "https://obs.ap-southeast-1.myhuaweicloud.com"
    }
    key = "envs/01-foundation/terraform.tfstate"

    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

# Provider config for the foundation env.
# Module 1 runs in the master account only — single provider, no aliases needed.
# Subsequent envs (03-identity, 04-perimeter, etc.) read the foundation outputs and
# configure additional provider aliases for cross-account access.

# Master account. NO default_tags here: the only taggable resource in this env
# is huaweicloud_organizations_account, and org accounts must stay UNTAGGED
# (default_tags would stamp the master tag set onto every created account).
# Master-account IC content keeps its tags via 03-identity's own provider.
provider "huaweicloud" {
  region = var.home_region
}
