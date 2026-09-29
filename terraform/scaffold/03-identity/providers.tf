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
    key = "envs/03-identity/terraform.tfstate"

    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

# Default provider = master account (IC content) -> master tags. Cross-account
# aliases (one per M1 account, IAM baseline) are GENERATED into
# providers.generated.tf and carry var.default_tags (member tags).

provider "huaweicloud" {
  region = var.home_region

  default_tags = var.master_default_tags
}
