---
name: huawei-cloud-landing-zone
description: >
  Huawei Cloud Landing Zone engineering: architecture patterns (accounts/OUs,
  hub-spoke network with Enterprise Router, security baseline, identity),
  Terraform implementation constraints (module composition, apply ordering,
  OBS state backend, cross-account assume-role, state surgery, billing modes),
  validation gates (platform rules, plan triage, drift, silent-failure traps),
  and delivery (LLD workbook, generated docs, handover artifact). Use for ANY
  landing-zone-level task on Huawei Cloud: designing an LZ, composing or
  reviewing env Terraform, debugging cross-account/SCP/backend errors,
  planning applies, state migrations, billing-mode changes, or preparing
  customer handover. For single-service HCL generation (one ECS/VPC/RDS
  resource), defer to the huawei-cloud-terraform-generator skill instead.
---

# Huawei Cloud Landing Zone [REUSABLE]

Landing-zone-level knowledge distilled from a production landing-zone
delivery: a 12-environment Terraform estate covering the 9 governance
domains of the Cloud Adoption Framework (CAF) across a multi-account
organization. The companion skill `huawei-cloud-terraform-generator`
covers per-service resource authoring; this skill covers how the services
compose into a landing zone.

## How to use this skill

Load only the asset(s) for the topic at hand:

| Phase | Topic | Asset |
|---|---|---|
| Intake | Questionnaire → draft spec, gap tracking, review loop | [assets/intake-questionnaire/](assets/intake-questionnaire/README.md) |
| Intake | Ad-hoc requests: required facts, never-invent rule | [assets/discovery-protocol/](assets/discovery-protocol/README.md) |
| Design | Accounts, OUs, delegated admin, enterprise projects | [assets/accounts-ous/](assets/accounts-ous/README.md) |
| Design | ER hub-and-spoke, route tables, centralized inspection | [assets/network-topology/](assets/network-topology/README.md) |
| Design | Hybrid connectivity: VPN automated, DC/CC boundary | [assets/hybrid-connectivity/](assets/hybrid-connectivity/README.md) |
| Design | Hub-resolver DNS + the unattached-spoke hazard | [assets/dns/](assets/dns/README.md) |
| Design | SCP guardrails: packing, tag SCPs, tenant quirks | [assets/scp-guardrails/](assets/scp-guardrails/README.md) |
| Design | Identity Center, EP-scoped permission sets, policy language | [assets/identity/](assets/identity/README.md) |
| Design | Log convergence, CTS, observability | [assets/observability/](assets/observability/README.md) |
| Design | CBR vaults/policies, OBS lifecycle, DR boundary | [assets/backup-dr/](assets/backup-dr/README.md) |
| Design | Firewall rule plane: groups, rule symmetry, SG interaction | [assets/cfw-rule-plane/](assets/cfw-rule-plane/README.md) |
| Design | Edge security: WAF, Anti-DDoS, SecMaster pending | [assets/edge-security/](assets/edge-security/README.md) |
| Build | Repo shape, codegen split, module/env patterns, tagging | [assets/repo-codegen/](assets/repo-codegen/README.md) |
| Build | Provider block: all six auth methods, provider arguments | [assets/provider-auth/](assets/provider-auth/README.md) |
| Build | OBS state backend, locking, state-key contracts | [assets/state-backend/](assets/state-backend/README.md) |
| Build | Cross-account providers: the two assume-role modes | [assets/cross-account/](assets/cross-account/README.md) |
| Build | Apply orchestration, runner, retries | [assets/apply-orchestration/](assets/apply-orchestration/README.md) |
| Build | CI credentials: OIDC → short-lived AK/SK, trust agencies | [assets/ci-credentials-oidc/](assets/ci-credentials-oidc/README.md) |
| Build | State surgery: env splits, moves, refresh-only, key contracts | [assets/state-surgery/](assets/state-surgery/README.md) |
| Build | Billing modes: charging_mode doctrine, BSS conversions | [assets/billing/](assets/billing/README.md) |
| Verify | Fresh-account preflight: what doesn't exist yet, capacity vs quota | [assets/fresh-account-preflight/](assets/fresh-account-preflight/README.md) |
| Verify | Spec validation, LZR rules, regression harness | [assets/validation-gates/](assets/validation-gates/README.md) |
| Verify | Cost estimation: rate card, what it can't price | [assets/pricing-cost/](assets/pricing-cost/README.md) |
| Verify | Plan triage, drift classes, review gates | [assets/plan-triage-drift/](assets/plan-triage-drift/README.md) |
| Verify | Silent-failure traps (no-error wrong behavior) | [assets/silent-failures/](assets/silent-failures/README.md) |
| Deliver | Artifact model, handover checklist, comment hygiene | [assets/artifact-handover/](assets/artifact-handover/README.md) |
| Deliver | Generated documents, LLD contract, Day-2 operations | [assets/documents-day2/](assets/documents-day2/README.md) |

## Non-negotiable constraints (memorize; details in the assets)

1. Provider `huaweicloud/huaweicloud ~> 1.87`, Terraform `>= 1.6.3`.
2. The Cloud Trace Service (CTS) **org tracker region is hard-coded** (`cn-north-4` or `ap-southeast-1`) — never a variable.
3. Service control policies (SCPs) use **v5 syntax** (`"Version": "5.0"`, `service:resourceType:action`).
4. The OBS S3-compatible state backend needs **all five `skip_*` flags** or `init` fails silently.
5. Cross-account = `assume_role { agency_name, domain_name }` — **never `role_arn`**; two assume modes exist, and picking the wrong one lands OBS buckets in the wrong account (see assets/cross-account).
6. **No native state locking** — serialize applies (CI concurrency group), back up state before every apply.
7. Envs apply **strictly in numeric order**; later envs read earlier outputs via `terraform_remote_state`.
8. Terraform 1.11+ against the OBS backend needs `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` and `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required`.
9. **Keys are contracts**: never rename a `backend.tf` state key, and never rename a `for_each` key that addresses live resources (renames plan destroy/create — see assets/state-surgery).
10. Logic lives in **codegen, not clever HCL** — emitted Terraform must be maintainable by an operator who has only the IaC.
11. **Never let Terraform place a BSS order.** A `postPaid -> prePaid` diff is a purchase, not a state fix — convert in the console, then `apply -refresh-only` (see assets/billing).

## How agents should reason about LZ decisions

1. **Constraint first**: check the non-negotiables above before proposing
   anything; most "creative" designs die on a platform cap.
2. **Provider docs are the source of truth**: consult the
   `terraform-provider-huaweicloud` repo's `docs/` tree before memory or web;
   the Go source (`huaweicloud/services/<svc>`) is the last resort — its Read
   functions decide drift behavior, and several diagnoses below came from it.
3. **Domain isolation**: a change belongs to exactly one domain module; if it
   needs two, it's probably an env-level composition concern.
4. **Blast-radius ordering**: keep replace-sensitive resources (VPN gateway
   public EIPs, CFW instance) in their own env/state so routine changes
   can't touch them.
5. **Deterministic over dynamic**: precompute at generation time; look up by
   name via data sources at plan time; hard-code what the platform fixes.
6. **Everything reversible has a documented rollback; everything irreversible
   gets a human gate.** Known-irreversible on this platform: account creation,
   poc-type enterprise projects (can never be disabled or destroyed), state
   moves/pushes, VPN gateway public EIP changes (force-replace = new public
   IPs = site down).

## Inputs this skill expects

- A requirement source: a filled assessment questionnaire (earliest), the customer low-level design (LLD) or spec (JSON or Excel), or a described target architecture.
- For implementation tasks: the env tree + module library layout (or intent to scaffold one).
- For validation/delivery tasks: access to plan JSON / state / the generated tree.

## Outputs it produces

- Architecture decisions with rationale anchored to the platform constraints.
- Env/module Terraform composed per the catalogue pattern (plain HCL + tfvars).
- Validation verdicts: rule findings, triage classes (benign / review / destructive), drift explanations.
- Delivery artifacts: LLD/spec content, doc-set inputs, handover checklists.

## Example prompts that should trigger this skill

- "Turn this filled assessment questionnaire into a draft landing-zone spec."
- "Design an account and network structure for a Huawei Cloud landing zone."
- "Why is my cross-account OBS bucket being created in the master account?"
- "Compose the env that deploys CFW rules on the hub firewall."
- "Review this plan for destructive changes before apply."
- "Why does `terraform init` fail with XAmzContentSHA256Mismatch?"
- "We converted the ECS fleet to monthly billing in the console — fix the code and state."
- "Split the VPN resources out of the network env without touching the cloud."
- "Prepare the handover package for the customer."

## Phase contract

| Phase | Entry criteria | Exit artifacts | Forbidden transitions |
|---|---|---|---|
| Intake | a requirement source (questionnaire, LLD, or ad-hoc request) | draft spec + decisions file | design without a decisions file |
| Design | draft spec + decisions file | resolved decisions + updated spec | build with open critical decisions |
| Build | spec validation passes with 0 errors | generated envs + fresh dependencies | plan/apply from a stale tree |
| Verify | built tree | clean plan triage + passing harness | apply with untriaged destructive changes |
| Deliver | applied + verified estate | evidence bundle + handover artifact | handover without verification evidence |

No phase may be skipped forward; stopping at any phase is always safe.
