# OBS S3-compat backend for Terraform state.
#
# Backend config is intentionally split out — fill in `backend.hcl` from the
# example file and run: terraform init -backend-config=backend.hcl
#
# The five skip_* flags are NON-NEGOTIABLE for OBS:
#   - skip_requesting_account_id     : OBS doesn't return STS account IDs
#   - skip_s3_checksum               : OBS doesn't support AWS SDK v2 checksums
#   - skip_region_validation         : OBS region IDs are not AWS region IDs
#   - skip_credentials_validation    : skips STS GetCallerIdentity (no STS)
#   - skip_metadata_api_check        : no IMDS on the runner side
#
# Also REQUIRED for Terraform 1.11+: set these env vars before `terraform init`:
#   $env:AWS_REQUEST_CHECKSUM_CALCULATION  = "when_required"
#   $env:AWS_RESPONSE_CHECKSUM_VALIDATION = "when_required"

terraform {
  backend "s3" {
    key = "envs/01-foundation/terraform.tfstate"

    # The following come from backend.hcl:
    #   bucket    = "..."
    #   region    = "..."
    #   endpoints = { s3 = "..." }

    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}
