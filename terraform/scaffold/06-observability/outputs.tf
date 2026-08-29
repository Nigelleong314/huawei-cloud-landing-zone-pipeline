# Central audit (module 6, in the CTS-admin account) outputs.
# Per-account ops (module 7) outputs are generated alongside the module calls in
# observability.generated.tf.
output "audit_bucket_name" { value = module.audit.audit_bucket_name }
output "audit_bucket_id" { value = module.audit.audit_bucket_id }
output "kms_key_ids" { value = module.audit.kms_key_ids }
output "cts_tracker_id" { value = module.audit.cts_tracker_id }
output "cts_log_group_id" { value = module.audit.cts_log_group_id }
output "cts_log_stream_id" { value = module.audit.cts_log_stream_id }

# LTS group name -> ID map for downstream consumers (07-security wires these
# into SecMaster cloud log resources). Published on the next apply.
output "lts_group_ids" {
  value = { (var.cts_log_group_name) = module.audit.cts_log_group_id }
}
