# Cross-account providers: the two assume-role modes [PLATFORM]

Both use master AK/SK + the member's `OrganizationAccountAccessAgency`;
they yield DIFFERENT credentials:

| Mode | Config | Yields | Safe for | Breaks on |
|---|---|---|---|---|
| Agency token | provider attributes `agency_name` + `agency_domain_name` | member-scoped IAM **token** | Organizations/SCP, IAM token ops, domain-scoped RMS, EPS, TMS | **OBS** (bucket lands in MASTER — signed with master keys), v5 IAM (`PAP5.0046`), org-scoped RMS |
| `assume_role` block | `assume_role { agency_name, domain_name }` | temp member **AK/SK + token** | everything, incl. OBS, v5 IAM, org-scoped RMS | — |

Rule: if a member-account env creates OBS buckets, v5 IAM agencies, or
org-scoped RMS → `assume_role` block. Always set
`default_tags = var.default_tags` on cross-account providers or the member's
require-mandatory-tags SCP denies creates (SYS.0403).

```hcl
provider "huaweicloud" {
  alias        = "member_admin"
  region       = var.home_region
  access_key   = var.master_access_key
  secret_key   = var.master_secret_key
  default_tags = var.default_tags          # REQUIRED or member SCPs deny creates
  assume_role {
    agency_name = "OrganizationAccountAccessAgency"
    domain_name = "<member-account-name>"
  }
}
```

## Owner-side vs member-side APIs

- ER route-table associations/propagations, RAM-share writes, and
  post-create tag updates on attachments of a shared ER must run under the
  HUB/owner provider — a member gets `common.01010013`. Put
  `ignore_changes = [tags]` on member-side attachments.
- Org-sharing enablement is master-account-only (404 from a member agency).
- Fresh-agency 403s right after account creation are transient — retry once.

## When the base credentials are themselves a session

Verified live-API behavior (level 4):

- **Real Identity Center session credentials** chain through all three
  modes: `assume_role { domain_name }`, `assume_role { domain_id }`, and the
  top-level `agency_name` + `agency_domain_name`.
- **A hand-made trust-agency session** (STS v5 `agencies/assume`) does not.
  The IAM 3.0 assume calls reject it with
  `IAM.0091, The token is unsupported for trust agency`; only
  `assume_role { agency_name, domain_id }` (the STS path) chains from it.
- **Never use a trust agency as an Identity Center stand-in when testing** —
  it fails modes that work in production.
- The operator's policy needs both `sts:agencies:assume` and
  `iam:tokens:assume`; the deny message calls the latter `iam:assume`.
