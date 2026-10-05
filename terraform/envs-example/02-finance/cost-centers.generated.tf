# --- Cost-center projects by account ---

# Account: Master
module "cost_centers_master" {
  source = "../../modules/financial"

  enable_multi_ep = true
  cost_centers    = var.cost_centers_by_account["master"]
}

# Account: EXAMPLE-LogArchive
module "cost_centers_acct_EXAMPLE_LogArchive" {
  source    = "../../modules/financial"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_LogArchive }

  enable_multi_ep = true
  cost_centers    = var.cost_centers_by_account["EXAMPLE-LogArchive"]
}

# Account: EXAMPLE-Security
module "cost_centers_acct_EXAMPLE_Security" {
  source    = "../../modules/financial"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Security }

  enable_multi_ep = true
  cost_centers    = var.cost_centers_by_account["EXAMPLE-Security"]
}

# Account: EXAMPLE-SharedInfra
module "cost_centers_acct_EXAMPLE_SharedInfra" {
  source    = "../../modules/financial"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_SharedInfra }

  enable_multi_ep = true
  cost_centers    = var.cost_centers_by_account["EXAMPLE-SharedInfra"]
}

# Account: EXAMPLE-Prod-A
module "cost_centers_acct_EXAMPLE_Prod_A" {
  source    = "../../modules/financial"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Prod_A }

  enable_multi_ep = true
  cost_centers    = var.cost_centers_by_account["EXAMPLE-Prod-A"]
}

# Account: EXAMPLE-Sandbox1
module "cost_centers_acct_EXAMPLE_Sandbox1" {
  source    = "../../modules/financial"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Sandbox1 }

  enable_multi_ep = true
  cost_centers    = var.cost_centers_by_account["EXAMPLE-Sandbox1"]
}
