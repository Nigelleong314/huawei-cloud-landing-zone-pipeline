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
    key                         = "envs/06-observability/terraform.tfstate"
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

# Per-account assume_role providers (audit_admin + ops accounts) live in
# providers.generated.tf.
