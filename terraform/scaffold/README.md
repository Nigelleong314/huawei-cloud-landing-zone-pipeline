# terraform/scaffold — the blank env scaffold

Env compositions for the module set in
`../modules/`. This tree is the template:
building a spec with `--scaffold-dir terraform/scaffold` copies these static
files into the new tree, then generates the per-env inputs next to them.

## Envs (apply order)

| Path | Module(s) called | Account(s) |
|---|---|---|
| `00-bootstrap/` | (none — state bucket only) | master |
| `01-foundation/` | M1 organization | master |
| `02-finance/` | M8 cost-center enterprise projects | master |
| `03-identity/` | M2 | master (Identity Center) + every account (IAM baseline) |
| `04-perimeter/` | M4 | master (SCPs) + every account (predefined tags fan-out) |
| `05-network/` | M3 hub + spokes | hub account + each spoke account |
| `06-observability/` | M6 audit + M7 ops + M12 log aggregation | log-archive / ops accounts |
| `07-security/` | M5 SecMaster | security account |
| `08-network-dns/` | M9 DNS zones + hybrid resolver | DNS account |
| `09-network-cfw/` | CFW rule plane on the 05-network hub firewall | hub account |
| `10-network-vpn/` | VPN gateways + customer gateways + connections | hub account |
| `11-network-sgacl/` | Workload security groups | per workload account |

(A tree may add its own hand-written envs beside these; the build leaves
them alone, and an export profile can leave them out with `skip_envs`.)

## Conventions

- Static files per env: `providers.tf` (provider requirements plus an inline
  `backend "s3"` block; the build fills in bucket and region, so
  `terraform init` needs no flags), `main.tf`, `variables.tf`, `outputs.tf`,
  plus `terraform.tfvars.example` documenting the expected shapes.
- Generated files per env (written by the pipeline, do not hand-edit):
  `terraform.tfvars.json`, `*.generated.tf`. Credentials are not among them:
  the provider reads `HW_ACCESS_KEY` / `HW_SECRET_KEY` / `HW_SECURITY_TOKEN`
  from the environment, and the backend the same keys as `AWS_*`.
- The build writes one root `.gitignore` into a new envs tree (state, plans,
  logs, caches); `.terraform.lock.hcl` is committed with each env.
- State backend: OBS S3-compatible, one bucket per org, key prefix per env.
- Cross-account access uses `assume_role` with `agency_name` + `domain_name`
  (never `role_arn`); one provider alias per target account.

## Required env vars before applying

Terraform 1.11+ with the OBS S3 backend needs:

```powershell
$env:AWS_REQUEST_CHECKSUM_CALCULATION  = "when_required"
$env:AWS_RESPONSE_CHECKSUM_VALIDATION = "when_required"
```

Without these, `terraform init` fails with `XAmzContentSHA256Mismatch` on
state push. `lzctl preflight` verifies them.

- Comments follow the artifact convention (`# --- Section ---`,
  `# Note: one sentence.`, short labels) and carry no history, roadmap notes
  or generator provenance. `py -m lz_pipeline.comment_lint terraform/scaffold`
  checks it; the exporter enforces it.
