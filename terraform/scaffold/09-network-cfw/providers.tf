provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key
}

# CFW rules deploy into var.cfw_account (the 05-network hub account that owns the
# firewall). assume_role BLOCK (temporary member AK/SK). NO default_tags by
# request: firewall rules stay untagged (safe — no cfw:* create action appears
# in the require_mandatory_tags SCP action list).
provider "huaweicloud" {
  alias      = "cfw"
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = var.cfw_account
  }
}
