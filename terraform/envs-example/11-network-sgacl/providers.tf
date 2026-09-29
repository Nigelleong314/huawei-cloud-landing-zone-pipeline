# --- Provider requirements and configuration ---

terraform {
  required_version = ">= 1.6.3"
  required_providers {
    huaweicloud = { source = "huaweicloud/huaweicloud", version = "~> 1.87" }
  }

  backend "s3" {
    # key is the HISTORICAL (pre-renumber) env name - it pins the live OBS state; never change
    key                         = "envs/11-network-sgacl/terraform.tfstate"
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

# Per-account assume_role providers (one per account with
# security groups) live in providers.generated.tf.
