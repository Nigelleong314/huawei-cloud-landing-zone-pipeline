output "ic_group_ids" {
  description = "IC group name → ID"
  value       = module.ic_content.group_ids
}

output "ic_permission_set_ids" {
  description = "IC permission set name → ID"
  value       = module.ic_content.permission_set_ids
}

# agencies_by_account (per-account service-agency URNs) is GENERATED into
# outputs.generated.tf, since the per-account iam_baseline modules are generated.
