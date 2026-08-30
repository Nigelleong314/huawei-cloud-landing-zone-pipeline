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

(A live tree may add a hand-scaffolded `12-workloads/` env; the scaffold does
not include one.)

## Conventions

- Static files per env: `versions.tf`, `providers.tf`, `backend.tf`,
  `main.tf`, `variables.tf`, `outputs.tf`, plus `backend.hcl.example` /
  `terraform.tfvars.example` documenting the expected shapes.
- Generated files per env (written by the pipeline, do not hand-edit):
  `terraform.tfvars.json`, `backend.hcl`, `*.generated.tf`,
  `secrets.auto.tfvars.json` (gitignored).
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
