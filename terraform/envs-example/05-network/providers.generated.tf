# --- Spoke account providers ---

# Account: EXAMPLE-Prod-A
provider "huaweicloud" {
  alias  = "spoke_EXAMPLE_Prod_A"
  region = var.home_region

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Prod-A"
  }
  # Mandatory resource tags
  default_tags = var.default_tags
}

# Account: EXAMPLE-Sandbox1
provider "huaweicloud" {
  alias  = "spoke_EXAMPLE_Sandbox1"
  region = var.home_region

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Sandbox1"
  }
  # Mandatory resource tags
  default_tags = var.default_tags
}
