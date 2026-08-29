# State bucket — created BEFORE any other env can run.
# This env uses LOCAL state (terraform.tfstate written to disk) since the
# remote backend doesn't exist yet. Commit `terraform.tfstate` to a secure
# location (NOT git) or migrate after the bucket exists.

resource "huaweicloud_obs_bucket" "tfstate" {
  bucket        = var.state_bucket_name
  storage_class = "STANDARD"
  acl           = "private"

  versioning = true

  encryption    = true
  sse_algorithm = "AES256" # SSE-OBS at bootstrap; switch to KMS later (chicken-egg)

  lifecycle_rule {
    name    = "expire-noncurrent"
    enabled = true
    noncurrent_version_expiration {
      days = 90
    }
    abort_incomplete_multipart_upload {
      days = 7
    }
  }

  tags = {
    ManagedBy = "terraform"
    Project   = "landing-zone"
    Purpose   = "tfstate"
  }
}

resource "huaweicloud_obs_bucket_bpa" "tfstate" {
  bucket                  = huaweicloud_obs_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
