# Foundation env: org bootstrap + accounts + IC instance + optional governance.
# Wraps modules-v2/organization (relative path).
#
# Apply time: ~10-15 minutes (faster than the RGC path; bottleneck is account
# email-confirmation + IC instance start).

module "org_foundation" {
  source = "../../modules/organization"

  environment = var.environment
  home_region = var.home_region

  enabled_policy_types      = var.enabled_policy_types
  organizational_units      = var.organizational_units
  core_accounts             = var.core_accounts
  workload_accounts         = var.workload_accounts
  cross_account_agency_name = var.cross_account_agency_name

  identity_center_alias    = var.identity_center_alias
  trusted_services         = var.trusted_services
  delegated_administrators = var.delegated_administrators

  tag_policies = var.tag_policies

  create_enterprise_project = var.create_enterprise_project
  enterprise_project_name   = var.enterprise_project_name
}
