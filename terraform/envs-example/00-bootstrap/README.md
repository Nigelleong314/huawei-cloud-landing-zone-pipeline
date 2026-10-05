# env 00-bootstrap

State bucket (chicken-egg). Uses **local** Terraform state.

## Apply

```powershell
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with a unique bucket name; credentials come from
# HW_ACCESS_KEY / HW_SECRET_KEY (+ HW_SECURITY_TOKEN) in the environment

terraform init
terraform plan
terraform apply
```

## After

1. Note the `state_bucket_name` output.
2. Every other env carries its backend inline in `providers.tf` (the build
   fills in the bucket), so `terraform init` needs no flags.
3. Store the local `terraform.tfstate` from this env securely (NOT in git).
   It is never part of the handover artifact; hand it over separately.

## ⚠ Required env vars for all other envs (Terraform 1.11+)

```powershell
$env:AWS_REQUEST_CHECKSUM_CALCULATION  = "when_required"
$env:AWS_RESPONSE_CHECKSUM_VALIDATION = "when_required"
```

Without these, `terraform init` on other envs fails with `XAmzContentSHA256Mismatch`.
