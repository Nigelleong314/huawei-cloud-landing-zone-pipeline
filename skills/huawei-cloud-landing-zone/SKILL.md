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

# Huawei Cloud Landing Zone

Landing-zone-level knowledge distilled from a production landing-zone
delivery: a 12-environment Terraform deployment covering the 9 governance
domains of the Cloud Adoption Framework (CAF) across a multi-account
organization. The companion skill `huawei-cloud-terraform-generator`
covers per-service resource authoring; this skill covers how the services
compose into a landing zone.

The `questionnaire-to-spec` skill drives the intake phase and depends on this skill's design rules; the dependency direction is questionnaire-to-spec -> huawei-cloud-landing-zone, never the reverse.

**The contract: this skill decides and asks; the pipeline (`lzctl`) executes and gates.** Judgment lands in reviewable artifacts (spec diffs, decisions files); every gate is an exit code; never bypass a gate by hand-editing generated output (`docs/skill-pipeline-contract.md` in the pipeline repo).

## How to use this skill

For every task, follow this operating loop:

1. **Place the task on the phase graph** (Phase contract below; authoritative copy in `schemas/phases.json`) — which phase is it in, and is its entry artifact present?
2. **Load only the asset(s)** matching the task from the capability table below.
3. **Execute through `lzctl`**, never around it — every action is a command a human could have typed.
4. **Use deterministic gate results, never subjective judgment**: exit codes and rule findings decide pass/fail (0 ok, 1 error, 2 changes, 3 destructive/blocked).
5. **Write judgment into artifacts** — spec edits, decision resolutions, triage notes — so a human can review the diff.
6. **Stop at gates you cannot pass**: an unresolved OPEN decision, a failing validation, an untriaged destructive plan. Ask; never guess, never bypass.

Tags: [DOMAIN] how to design a landing zone · [PLATFORM] verified Huawei Cloud behavior · [IMPLEMENTATION] how this pipeline behaves · [RUNBOOK] operational procedure.

| Phase | Capability | Input | Output | Asset |
|---|---|---|---|---|
| intake | Convert questionnaire to spec | filled questionnaire | draft spec + decisions file | [assets/intake-questionnaire/](assets/intake-questionnaire/README.md) |
| intake | Extract facts from ad-hoc asks | chat/email/ticket request | gap list + questions to ask | [assets/discovery-protocol/](assets/discovery-protocol/README.md) |
| design | Structure accounts and OUs | org + governance requirements | account/OU/EP decisions | [assets/accounts-ous/](assets/accounts-ous/README.md) |
| design | Design hub-spoke network | spec network sheets | ER + route-table decisions | [assets/network-topology/](assets/network-topology/README.md) |
| design | Wire on-prem connectivity | site/peer details | VPN design, DC/CC boundary | [assets/hybrid-connectivity/](assets/hybrid-connectivity/README.md) |
| design | Design hub-resolver DNS | zones + spoke attachment map | DNS env design | [assets/dns/](assets/dns/README.md) |
| design | Author SCP guardrails | governance requirements | packed v5 SCP set | [assets/scp-guardrails/](assets/scp-guardrails/README.md) |
| design | Scope identity and permission sets | roles/groups requirements | permission-set decisions | [assets/identity/](assets/identity/README.md) |
| design | Converge logs and audit | log sources + account map | log-convergence design | [assets/observability/](assets/observability/README.md) |
| design | Size backup and DR | retention/RPO requirements | vault + policy spec fields | [assets/backup-dr/](assets/backup-dr/README.md) |
| design | Compose firewall rule plane | traffic flow matrix | group/rule composition | [assets/cfw-rule-plane/](assets/cfw-rule-plane/README.md) |
| design | Protect the internet edge | exposed domains/EIPs | WAF + Anti-DDoS design | [assets/edge-security/](assets/edge-security/README.md) |
| build | Shape repo and codegen | spec + module library | generated env tree | [assets/repo-codegen/](assets/repo-codegen/README.md) |
| build | Configure provider auth | execution context | provider block choice | [assets/provider-auth/](assets/provider-auth/README.md) |
| build | Configure OBS state backend | backend.tf, init errors | working backend config | [assets/state-backend/](assets/state-backend/README.md) |
| build | Pick cross-account assume mode | env's resource types | correct provider config | [assets/cross-account/](assets/cross-account/README.md) |
| build | Wire OIDC CI credentials | CI platform + account map | trust-agency chain | [assets/ci-credentials-oidc/](assets/ci-credentials-oidc/README.md) |
| deploy | Run ordered applies | built tree + deps.json | safe apply run | [assets/apply-orchestration/](assets/apply-orchestration/README.md) |
| deploy | Move state without cloud changes | state files + target layout | state-mv runbook | [assets/state-surgery/](assets/state-surgery/README.md) |
| deploy | Absorb billing-mode changes | console conversion + plan diff | per-resource code/state fix | [assets/billing/](assets/billing/README.md) |
| verify_pre | Preflight a fresh tenant | new account access | preflight checklist results | [assets/fresh-account-preflight/](assets/fresh-account-preflight/README.md) |
| verify_pre | Validate spec and generated Terraform | spec + generated tree | rule findings, gate verdicts | [assets/validation-gates/](assets/validation-gates/README.md) |
| verify_pre | Estimate plan cost | plan JSON + rate card | advisory cost summary | [assets/pricing-cost/](assets/pricing-cost/README.md) |
| verify_pre / verify_post | Triage plans and drift | plan JSON | triage verdicts | [assets/plan-triage-drift/](assets/plan-triage-drift/README.md) |
| verify_post | Catch no-error wrong behavior | clean plan/apply | trap findings | [assets/silent-failures/](assets/silent-failures/README.md) |
| deliver | Build handover artifact | working tree | release artifact | [assets/artifact-handover/](assets/artifact-handover/README.md) |
| deliver | Generate delivery documents | tfvars + pulled state | doc set + LLD workbook | [assets/documents-day2/](assets/documents-day2/README.md) |

(Phase labels are the exact names from `schemas/phases.json`.)

## Invocation

`/huawei-cloud-landing-zone [status|advance|plan|verify|docs] [target] [key=value...]`

Natural-language requests trigger this skill without any command; the explicit
form exists for precision. Actions:

| Action | Scope | What it runs |
|---|---|---|
| *(none)* or `status` | **Completely read-only.** Place the workspace on the phase graph, run the gates, report state + the one next action. Also detects an interrupted apply (lock file, `lzctl-logs/` tail, `state-backups/`) and presents the recovery procedure — inspection and instructions only, never an automatic resume or reapply. | `lzctl validate`, decisions-file inspection, `lzctl order` |
| `advance` | **Local generation only** — from the current phase up to the next decision gate or the cloud boundary, whichever comes first. Never contacts the cloud; stops before the first authenticated plan and says exactly what the operator does next. | `lzctl intake` / `assess` / `validate` / `build` / `preflight` as the phase requires |
| `plan [env[,env...]\|all]` | May contact the cloud and write plan artifacts. Preflight, ordered plans, triage summary with exit-code reading. | `lzctl preflight`, `plan`, `triage` |
| `verify` | Post-apply verification, drift sweep, and (on request) the evidence bundle. | `lzctl verify`, `drift`, `report` |
| `docs` | **Local customer-document regeneration only.** No drift sweep, no cloud contact. | `lzctl docs` |

Qualifiers are an **allowlist**, mapped one-to-one onto CLI arguments —
`spec=<path>` (`--spec`), `envs=<dir>` (`--envs-dir`),
`customer=<id>` (`--customer`). Quoted paths are supported
(`spec="C:\Customer Files\lz.spec.acme.json"`). An unknown key, a duplicate
key, or an ambiguous path is reported back, never forwarded to the CLI.

**This skill never executes `terraform apply` (nor `lzctl apply`).** It stops
at the apply gate and presents the operator command; the typed destructive
confirmation is always a human at a terminal. There is no `resume` action —
an interrupted apply is a recovery incident handled by `status` as described
above.

## Companion skill (optional)

The `huawei-cloud-terraform-generator` skill (separate distribution, not included in this repository) generates single-service resources with per-service references and region-availability verification. It is optional — this skill and the pipeline are fully usable without it; without it, author single-resource HCL from the provider docs per the evidence hierarchy below.

## Non-negotiable constraints — check these before proposing or executing any change

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

1. **Check constraints first**: check the non-negotiables above before
   proposing anything; many proposed designs fail against platform limits.
2. **Evidence hierarchy**: (1) current Huawei Cloud service documentation,
   (2) current Terraform provider documentation, (3) provider source when the
   docs are silent — its Read functions decide drift behavior, (4) verified
   live-API behavior, (5) this pipeline's implementation constraints,
   (6) historical incident knowledge. Cite the level you used.
3. **Domain isolation**: a change belongs to exactly one domain module; if it
   needs two, it's probably an env-level composition concern.
4. **Blast-radius ordering**: keep replace-sensitive resources (VPN gateway
   public EIPs, CFW instance) in their own env/state so routine changes
   can't touch them.
5. **Deterministic over dynamic**: precompute at generation time; look up by
   name via data sources at plan time; hard-code what the platform fixes.
6. **Everything reversible has a documented rollback; everything irreversible
   gets a human gate.** Known irreversible operations on this platform: account creation,
   `poc`-type (PoC) enterprise projects (can never be disabled or destroyed), state
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
| intake | a requirement source (questionnaire, LLD, or described target) | neutral draft spec + decisions files (ANSWERED/DEFAULTED/OPEN) | design without a decisions file |
| design | draft spec + decisions files | OPEN items resolved; validation passes with 0 errors | build with unresolved OPEN decisions (`lzctl build` exits 3) |
| build | spec validating with 0 errors | generated envs + fresh deps.json | plan/apply from a stale tree |
| verify_pre | built tree | clean plan triage + passing harness | apply with untriaged destructive changes |
| deploy | reviewed plan + approvals (typed confirm for destructive) | applied envs in dependency order + state backups + run logs | applying out of dependency order |
| verify_post | applied infrastructure | every env clean or known-benign | deliver without verification |
| deliver | verified infrastructure | evidence bundle + generated docs + handover artifact | handover without verification evidence |

No phase may be skipped forward. A workflow may stop at any GATE, but an interrupted deployment can leave a partially applied deployment and must be resumed through verify_post (`lzctl verify`) before further changes.

The same phase graph is machine-readable at `schemas/phases.json`; skill, CLI docs, and eval fixtures share it.
