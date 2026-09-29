# --- Provider requirements and configuration ---

terraform {
  required_version = ">= 1.6.3"
  required_providers {
    huaweicloud = { source = "huaweicloud/huaweicloud", version = "~> 1.87" }
  }

  backend "s3" {
    key = "envs/08-network-dns/terraform.tfstate"

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

# DNS deploys into var.dns_account (assumes that account's OrganizationAccountAccessAgency).
# Uses the assume_role BLOCK (temporary member AK/SK) — the agency_name attribute form
# yields only an agency token, which 404s on several AK/SK-signed APIs. default_tags is
# set so taggable DNS resources carry the mandatory tags the require_mandatory_tags SCP
# expects. domain_name = the MEMBER account.
provider "huaweicloud" {
  alias  = "dns"
  region = var.home_region

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.dns_account
  }

  default_tags = var.default_tags
}
