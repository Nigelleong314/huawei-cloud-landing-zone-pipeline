# --- Central audit - EXAMPLE-Security ---
module "audit" {
  source    = "../../modules/compliance-audit"
  providers = { huaweicloud = huaweicloud.audit_admin }

  environment                = var.environment
  home_region                = var.home_region
  account_name               = "EXAMPLE-Security"
  audit_bucket_name          = var.audit_bucket_name
  kms_audit_alias            = var.kms_audit_alias
  member_account_ids         = local.member_account_ids
  audit_retention_days       = var.audit_retention_days
  audit_cold_after_days      = var.audit_cold_after_days
  kms_pending_days           = var.kms_pending_days
  audit_bucket_force_destroy = var.audit_bucket_force_destroy

  # Key-event notification topic
  cts_notifications          = var.cts_notifications
  cts_notification_topic_urn = module.ops_acct_EXAMPLE_Security.smn_topic_urn
}

module "ops_acct_EXAMPLE_Security" {
  source    = "../../modules/ops-monitoring"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Security }

  environment      = var.environment
  account_name     = "EXAMPLE-Security"
  topic_name       = var.topic_name
  subscribers      = var.subscribers
  one_click_alarms = var.one_click_alarms
}

module "ops_acct_EXAMPLE_Prod_A" {
  source    = "../../modules/ops-monitoring"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Prod_A }

  environment      = var.environment
  account_name     = "EXAMPLE-Prod-A"
  topic_name       = var.topic_name
  subscribers      = var.subscribers
  one_click_alarms = var.one_click_alarms
}

# --- Account audit tracker - EXAMPLE-Sandbox1 ---
module "cts_tracker_acct_EXAMPLE_Sandbox1" {
  source    = "../../modules/cts-tracker"
  providers = { huaweicloud = huaweicloud.acct_EXAMPLE_Sandbox1 }

  environment = var.environment
}
