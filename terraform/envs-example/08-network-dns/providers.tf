provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key
}

# DNS deploys into var.dns_account (assumes that account's OrganizationAccountAccessAgency).
# Uses the assume_role BLOCK (temporary member AK/SK) — the agency_name attribute form
# yields only an agency token, which 404s on several AK/SK-signed APIs. default_tags is
# set so taggable DNS resources carry the mandatory tags the require_mandatory_tags SCP
# expects. domain_name = the MEMBER account.
provider "huaweicloud" {
  alias      = "dns"
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.dns_account
  }

  default_tags = var.default_tags
}
