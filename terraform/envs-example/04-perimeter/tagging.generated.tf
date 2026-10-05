# --- Predefined tags by account ---

# Account: Master
module "predef_tags_master" {
  source = "../../modules/perimeter"

  enable_scps            = false
  enable_predefined_tags = true
  predefined_tags        = var.predefined_tags
}

# Account: EXAMPLE-LogArchive
module "predef_tags_acct_EXAMPLE_LogArchive" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_LogArchive }

  enable_scps            = false
  enable_predefined_tags = true
  predefined_tags        = var.predefined_tags
}

# Account: EXAMPLE-Security
module "predef_tags_acct_EXAMPLE_Security" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Security }

  enable_scps            = false
  enable_predefined_tags = true
  predefined_tags        = var.predefined_tags
}

# Account: EXAMPLE-SharedInfra
module "predef_tags_acct_EXAMPLE_SharedInfra" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_SharedInfra }

  enable_scps            = false
  enable_predefined_tags = true
  predefined_tags        = var.predefined_tags
}

# Account: EXAMPLE-Prod-A
module "predef_tags_acct_EXAMPLE_Prod_A" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Prod_A }

  enable_scps            = false
  enable_predefined_tags = true
  predefined_tags        = var.predefined_tags
}

# Account: EXAMPLE-Sandbox1
module "predef_tags_acct_EXAMPLE_Sandbox1" {
  source    = "../../modules/perimeter"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Sandbox1 }

  enable_scps            = false
  enable_predefined_tags = true
  predefined_tags        = var.predefined_tags
}
