# Accounts, OUs, delegated administration [REUSABLE]

## The 9 governance domains → module map

Cut the landing zone by Cloud Adoption Framework (CAF) governance domain:
one Terraform module per domain concern, composed by numbered environment
directories:

| Domain | Module(s) | Env |
|---|---|---|
| Organization & accounts | `organization` (org, OUs, accounts, Identity Center bootstrap, tag policies) | 01 |
| Financial governance | `financial` (cost-center enterprise projects) | 02 |
| Identity | `identity` (Identity Center users/groups/permission sets + per-account IAM baseline) | 03 |
| Perimeter governance | `perimeter` (SCP guardrails, predefined tags, Config/RMS org recorder + conformance) | 04 |
| Network | `network` (Enterprise Router hub, spoke VPCs, Cloud Firewall instance, NAT/ELB/EIP, RAM sharing, flow logs) | 05 |
| Observability | `compliance-audit` + `cts-tracker` + `ops-monitoring` + `log-aggregation` | 06 |
| Security services | `security` (SecMaster) + `edge-protection` (Anti-DDoS, WAF) | 07 |
| DNS | `dns` (public/private zones, records, hybrid resolver) | 08 |
| Firewall policy | `cfw` (the rule plane on the 05 firewall) | 09 |
| Hybrid connectivity | `vpn` (site-to-cloud VPN) | 10 |
| Workload network policy | `secgroups` (workload security groups) | 11 |

Modules are named by domain (no numbers); only envs are numbered. Env
numbers ARE the apply order.

## Account and OU structure

- OU depth ≤ 2, no parent cycles. Typical OUs: Security, Infrastructure,
  Workloads, Sandbox.
- Core accounts: log-archive (LTS delegated admin + archive bucket),
  security (CTS/Config delegated admin, SecMaster), shared-infra (network
  hub). Workload accounts hang off Workloads/Sandbox OUs.
- Account names 6–32 chars; unique root emails. Account **email is ForceNew**
  and account deletion is unsupported — an email change made in the console
  MUST be reconciled into spec + state (refresh/state surgery) or the next
  plan proposes 1:1 replacements that can only fail.
- Every member account gets an auto-created
  `OrganizationAccountAccessAgency` — that agency IS the cross-account
  access model (no per-account credentials, ever).
- Delegated administration: hand each org service (CTS, Config, LTS, RAM) to
  the right member account via `trusted_service` + `delegated_administrator`;
  log tooling deploys INTO the delegated-admin account.

## Enterprise projects (EPS)

- **The EPS authority grant is asynchronous**: an enterprise project created
  seconds after the grant fails with `EPS.0004 "Permission error"` on fresh
  accounts. Add a one-time sleep after the grant. Deleting the grant resource
  does NOT revoke the authority.
- **poc-type enterprise projects are permanent**: they cannot be disabled
  (`EPS.0614`), so `terraform destroy` fails forever and orphans them outside
  state. Name poc EPs right the first time; treat their creation as an
  irreversible action requiring a human gate.
