# --- Audit and monitoring account providers ---

# Account: EXAMPLE-Security
provider "huaweicloud" {
  alias  = "audit_admin"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Security"
  }
}

# Account: EXAMPLE-LogArchive
provider "huaweicloud" {
  alias  = "lts_admin"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-LogArchive"
  }
}

# Account: EXAMPLE-Security
provider "huaweicloud" {
  alias  = "acct_EXAMPLE_Security"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Security"
  }
}

# Account: EXAMPLE-Prod-A
provider "huaweicloud" {
  alias  = "acct_EXAMPLE_Prod_A"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Prod-A"
  }
}

# Account: EXAMPLE-Sandbox1
provider "huaweicloud" {
  alias  = "acct_EXAMPLE_Sandbox1"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Sandbox1"
  }
}

# Account: EXAMPLE-SharedInfra
provider "huaweicloud" {
  alias  = "acct_EXAMPLE_SharedInfra"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-SharedInfra"
  }
}
