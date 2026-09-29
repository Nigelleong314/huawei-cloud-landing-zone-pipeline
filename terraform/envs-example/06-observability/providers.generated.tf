# --- Audit and monitoring account providers ---

# assume_role providers: central audit (CTS-admin) + LTS admin (log aggregation)
# + per-account ops / cts-no-transfer / log-converge sources.

provider "huaweicloud" {
  alias        = "audit_admin"
  region       = var.home_region
  default_tags = var.default_tags # mandatory tags so the require_mandatory_tags SCP allows creates

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Security"
  }
}

provider "huaweicloud" {
  alias        = "lts_admin"
  region       = var.home_region
  default_tags = var.default_tags # mandatory tags so the require_mandatory_tags SCP allows creates

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-LogArchive"
  }
}

provider "huaweicloud" {
  alias        = "acct_EXAMPLE_Security"
  region       = var.home_region
  default_tags = var.default_tags # mandatory tags so the require_mandatory_tags SCP allows creates

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Security"
  }
}

provider "huaweicloud" {
  alias        = "acct_EXAMPLE_Prod_A"
  region       = var.home_region
  default_tags = var.default_tags # mandatory tags so the require_mandatory_tags SCP allows creates

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Prod-A"
  }
}

provider "huaweicloud" {
  alias        = "acct_EXAMPLE_Sandbox1"
  region       = var.home_region
  default_tags = var.default_tags # mandatory tags so the require_mandatory_tags SCP allows creates

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Sandbox1"
  }
}

provider "huaweicloud" {
  alias        = "acct_EXAMPLE_SharedInfra"
  region       = var.home_region
  default_tags = var.default_tags # mandatory tags so the require_mandatory_tags SCP allows creates

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-SharedInfra"
  }
}
