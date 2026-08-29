# Env outputs — consumed by downstream envs via terraform_remote_state.

output "organization_id" { value = module.org_foundation.organization_id }
output "organization_urn" { value = module.org_foundation.organization_urn }
output "master_account_id" { value = module.org_foundation.master_account_id }
output "master_account_name" { value = module.org_foundation.master_account_name }
output "root_id" { value = module.org_foundation.root_id }
output "ou_ids" { value = module.org_foundation.ou_ids }
output "workloads_ou_id" { value = module.org_foundation.workloads_ou_id }
output "accounts" { value = module.org_foundation.accounts }
output "identity_store_id" { value = module.org_foundation.identity_store_id }
output "identity_center_instance_urn" { value = module.org_foundation.identity_center_instance_urn }
output "identity_center_instance_id" { value = module.org_foundation.identity_center_instance_id }
output "enterprise_project_id" { value = module.org_foundation.enterprise_project_id }
output "custom_tag_policy_ids" { value = module.org_foundation.custom_tag_policy_ids }
output "cross_account_agency_name" { value = module.org_foundation.cross_account_agency_name }
output "home_region" { value = var.home_region }
