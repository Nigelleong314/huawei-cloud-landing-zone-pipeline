# --- Config recorders by account ---
# Note: Member recorders use the central EXAMPLE-Security bucket.

provider "huaweicloud" {
  alias  = "config_admin"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Security"
  }
}

# --- Central Config setup - EXAMPLE-Security ---
module "config_setup" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.config_admin }

  enable_scps            = false
  enable_predefined_tags = false
  enable_config          = true
  home_region            = var.home_region
  org_id                 = local.foundation.organization_id
  config = merge(var.config, {
    recorder_bucket_writer_domains = [for k, v in local.foundation.accounts : v.id]
  })
  # Conformance packs managed by config_packs
  conformance_packs = []
}

# --- Config recorder - EXAMPLE-LogArchive ---
provider "huaweicloud" {
  alias  = "config_rec_EXAMPLE_LogArchive"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-LogArchive"
  }
}

module "config_recorder_acct_EXAMPLE_LogArchive" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.config_rec_EXAMPLE_LogArchive }

  enable_scps            = false
  enable_predefined_tags = false
  enable_config          = true
  home_region            = var.home_region
  config                 = merge(var.config, { create_recorder_bucket = false, enable_aggregator = false })
  conformance_packs      = []

  # Note: Create the central bucket and policy before member recorders.
  depends_on = [module.config_setup]
}

# --- Config recorder - EXAMPLE-SharedInfra ---
provider "huaweicloud" {
  alias  = "config_rec_EXAMPLE_SharedInfra"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-SharedInfra"
  }
}

module "config_recorder_acct_EXAMPLE_SharedInfra" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.config_rec_EXAMPLE_SharedInfra }

  enable_scps            = false
  enable_predefined_tags = false
  enable_config          = true
  home_region            = var.home_region
  config                 = merge(var.config, { create_recorder_bucket = false, enable_aggregator = false })
  conformance_packs      = []

  # Note: Create the central bucket and policy before member recorders.
  depends_on = [module.config_setup]
}

# --- Config recorder - EXAMPLE-Prod-A ---
provider "huaweicloud" {
  alias  = "config_rec_EXAMPLE_Prod_A"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Prod-A"
  }
}

module "config_recorder_acct_EXAMPLE_Prod_A" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.config_rec_EXAMPLE_Prod_A }

  enable_scps            = false
  enable_predefined_tags = false
  enable_config          = true
  home_region            = var.home_region
  config                 = merge(var.config, { create_recorder_bucket = false, enable_aggregator = false })
  conformance_packs      = []

  # Note: Create the central bucket and policy before member recorders.
  depends_on = [module.config_setup]
}

# --- Config recorder - EXAMPLE-Sandbox1 ---
provider "huaweicloud" {
  alias  = "config_rec_EXAMPLE_Sandbox1"
  region = var.home_region
  # Mandatory resource tags
  default_tags = var.default_tags

  assume_role {
    agency_name = local.foundation.cross_account_agency_name
    domain_name = "EXAMPLE-Sandbox1"
  }
}

module "config_recorder_acct_EXAMPLE_Sandbox1" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.config_rec_EXAMPLE_Sandbox1 }

  enable_scps            = false
  enable_predefined_tags = false
  enable_config          = true
  home_region            = var.home_region
  config                 = merge(var.config, { create_recorder_bucket = false, enable_aggregator = false })
  conformance_packs      = []

  # Note: Create the central bucket and policy before member recorders.
  depends_on = [module.config_setup]
}

# --- Organization conformance packs ---
# Note: All central and member recorders must exist first.
module "config_packs" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.config_admin }

  enable_scps            = false
  enable_predefined_tags = false
  enable_config          = true
  home_region            = var.home_region
  org_id                 = local.foundation.organization_id
  config                 = merge(var.config, { enable_recorder = false, create_recorder_bucket = false, create_recorder_agency = false, enable_aggregator = false })
  # Excluded account resolution
  # Note: Names resolve to domain IDs; explicit IDs pass through. Master is excluded.
  conformance_packs = [for p in var.conformance_packs : merge(p, {
    excluded_accounts = concat(
      [for a in try(p.excluded_accounts, []) : can(regex("^[0-9a-f]{32}$", a)) ? a : local.foundation.accounts[a].id],
      [local.foundation.master_account_id],
    )
  })]

  depends_on = [module.config_setup, module.config_recorder_acct_EXAMPLE_LogArchive, module.config_recorder_acct_EXAMPLE_SharedInfra, module.config_recorder_acct_EXAMPLE_Prod_A, module.config_recorder_acct_EXAMPLE_Sandbox1]
}
