# --- IAM baseline by account ---

# Account: Master
module "iam_baseline_master" {
  source = "../../modules/identity"

  environment         = var.environment
  enable_iam_baseline = true
  service_agencies    = var.service_agencies != null ? var.service_agencies : null
  iam_login_policy    = var.iam_login_policy
}

# Account: EXAMPLE-LogArchive
module "iam_baseline_acct_EXAMPLE_LogArchive" {
  source    = "../../modules/identity"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_LogArchive }

  environment         = var.environment
  enable_iam_baseline = true
  service_agencies    = var.service_agencies != null ? var.service_agencies : null
  iam_login_policy    = var.iam_login_policy
}

# Account: EXAMPLE-Security
module "iam_baseline_acct_EXAMPLE_Security" {
  source    = "../../modules/identity"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Security }

  environment         = var.environment
  enable_iam_baseline = true
  service_agencies    = var.service_agencies != null ? var.service_agencies : null
  iam_login_policy    = var.iam_login_policy
}

# Account: EXAMPLE-SharedInfra
module "iam_baseline_acct_EXAMPLE_SharedInfra" {
  source    = "../../modules/identity"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_SharedInfra }

  environment         = var.environment
  enable_iam_baseline = true
  service_agencies    = var.service_agencies != null ? var.service_agencies : null
  iam_login_policy    = var.iam_login_policy
}

# Account: EXAMPLE-Prod-A
module "iam_baseline_acct_EXAMPLE_Prod_A" {
  source    = "../../modules/identity"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Prod_A }

  environment         = var.environment
  enable_iam_baseline = true
  service_agencies    = var.service_agencies != null ? var.service_agencies : null
  iam_login_policy    = var.iam_login_policy
}

# Account: EXAMPLE-Sandbox1
module "iam_baseline_acct_EXAMPLE_Sandbox1" {
  source    = "../../modules/identity"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Sandbox1 }

  environment         = var.environment
  enable_iam_baseline = true
  service_agencies    = var.service_agencies != null ? var.service_agencies : null
  iam_login_policy    = var.iam_login_policy
}
