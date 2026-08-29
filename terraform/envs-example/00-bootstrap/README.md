# env 00-bootstrap

State bucket (chicken-egg). Uses **local** Terraform state.

## Apply

```powershell
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with your AK/SK and a unique bucket name

terraform init
terraform plan
terraform apply
```

## After

1. Note the `state_bucket_name` output.
2. Copy `backend.hcl.example` → `backend.hcl` in each other env, fill in the
   bucket name.
3. Each other env runs `terraform init -backend-config=backend.hcl`.
4. Store the local `terraform.tfstate` from this env securely (NOT in git).

## ⚠ Required env vars for all other envs (Terraform 1.11+)

```powershell
$env:AWS_REQUEST_CHECKSUM_CALCULATION  = "when_required"
$env:AWS_RESPONSE_CHECKSUM_VALIDATION = "when_required"
```

Without these, `terraform init` on other envs fails with `XAmzContentSHA256Mismatch`.
