provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key

  default_tags = var.default_tags
}

provider "huaweicloud" {
  alias              = "lz_security"
  region             = var.home_region
  access_key         = var.master_access_key
  secret_key         = var.master_secret_key
  domain_name        = local.foundation.master_account_name
  agency_name        = local.foundation.cross_account_agency_name
  default_tags       = var.default_tags
  agency_domain_name = var.security_account
}

# Edge protection (module 13) deploys into the 05-network HUB account: the
# Anti-DDoS EIPs and the WAF VPC live there. assume_role block (temporary member
# AK/SK) like 05-network's vpn provider; default_tags so the require_mandatory_tags SCP allows creates.
provider "huaweicloud" {
  alias      = "hub"
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.hub_account
  }

  default_tags = var.default_tags
}
