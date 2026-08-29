# State backend: OBS, S3-compatible [REUSABLE]

```hcl
terraform {
  backend "s3" {
    # bucket / key / region elided; endpoint: s3 = "https://obs.<region>.myhuaweicloud.com"
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}
```

- All five `skip_*` flags or init fails in confusing ways.
- Terraform 1.11+: set `AWS_REQUEST_CHECKSUM_CALCULATION` and
  `AWS_RESPONSE_CHECKSUM_VALIDATION` to `when_required` or state push dies
  with `XAmzContentSHA256Mismatch`.
- **No native locking** → one apply at a time org-wide (CI concurrency
  group), advisory lock on the runner, `terraform state pull` backup before
  every apply, bucket versioning on.
- **State keys are permanent contracts.** Directories may be renamed; keys
  never. A comment in each backend.tf should say so. A new env gets a NEW
  key; a renamed env keeps its historical key forever.
- Backend tooling (state backup scripts, doc generators reading state) does
  not inherit Terraform's credentials — export the master AK/SK as
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (plus the two checksum vars)
  from the env's secrets file, without ever printing the values.
