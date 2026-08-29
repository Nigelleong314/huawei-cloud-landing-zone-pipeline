output "state_bucket_name" {
  value       = huaweicloud_obs_bucket.tfstate.bucket
  description = "Name of the OBS state bucket. Use this in backend.hcl for all other envs."
}

output "state_bucket_endpoint" {
  value       = "https://obs.${var.home_region}.myhuaweicloud.com"
  description = "OBS S3-compat endpoint for backend.hcl"
}
