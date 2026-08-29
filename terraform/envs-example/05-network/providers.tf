provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key
}

# Hub deploys into var.hub_account (assumes that account's OrganizationAccountAccessAgency).
# Uses the assume_role BLOCK (not the agency_name/agency_domain_name attribute form):
# it yields a TEMPORARY member AK/SK, which RAM (resource share) and other AK/SK-signed
# services require. The attribute form yields only an agency token, which 404s on RAM
# ("not found for http header"). domain_name = the MEMBER account.
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

# Spoke providers (one per distinct spoke account, WITH default_tags — required or
# the member's require_mandatory_tags SCP denies creates; per-row Tags override
# per-key) are GENERATED into providers.generated.tf from the SpokeVPCs table.
