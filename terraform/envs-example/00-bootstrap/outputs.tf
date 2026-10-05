# --- Bootstrap outputs ---

output "state_bucket_name" {
  value       = huaweicloud_obs_bucket.tfstate.bucket
  description = "Name of the OBS state bucket that every other env's backend uses."
}

output "state_bucket_endpoint" {
  value       = "https://obs.${var.home_region}.myhuaweicloud.com"
  description = "OBS S3-compat endpoint of the state backend"
}
