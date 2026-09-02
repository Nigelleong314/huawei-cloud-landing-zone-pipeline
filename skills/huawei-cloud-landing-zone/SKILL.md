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

1. **Place the task on the phase graph** — run `lzctl status --json` (read-only) and render it per the Rendering section below; it answers which phase the workspace is in, what needs a recheck or is blocked, and what the next command is. The contract is below; the authoritative copy is `schemas/phases.json`.
2. **Load only the asset(s)** matching the task from the capability table below.
3. **Execute through `lzctl`**, never around it — every action is a command a human could have typed.
4. **Use deterministic gate results, never subjective judgment**: exit codes and rule findings decide pass/fail (0 ok, 1 error, 2 changes, 3 destructive/blocked).
5. **Write judgment into artifacts** — spec edits, decision resolutions, triage notes — so a human can review the diff.
6. **Stop at gates you cannot pass**: an unresolved OPEN decision, an unfilled gap value, a failing validation, an untriaged destructive plan. Ask; never guess, never bypass — and when the missing answer is the customer's to give, hand them the app (see "The app" below) rather than a JSON file to edit.

Tags: [DOMAIN] how to design a landing zone · [PLATFORM] verified Huawei Cloud behavior · [IMPLEMENTATION] how this pipeline behaves · [RUNBOOK] operational procedure.

| Phase | Capability | Input | Output | Asset |
|---|---|---|---|---|
| intake | Convert questionnaire to spec | filled questionnaire | draft spec + decisions file | [assets/intake-questionnaire/](assets/intake-questionnaire/README.md) |
| intake | Extract facts from ad-hoc asks | chat/email/ticket request | gap list + questions to ask | [assets/discovery-protocol/](assets/discovery-protocol/README.md) |
| intake / design | Have a human review the draft and fill gap values | draft spec + decisions agenda | human-approved spec, gaps filled | "The app" section below (`lz-app`) |
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
| *(none)* or `status` | **Completely read-only.** Place the workspace on the phase graph, run the gates, report state + the one next action. Also detects an interrupted apply (lock file, `lzctl-logs/` tail, `state-backups/`) and presents the recovery procedure — inspection and instructions only, never an automatic resume or reapply. | `lzctl status`, `lzctl validate`, `lzctl order` |
| `advance` | **Local generation only** — from the current phase up to the next decision gate or the cloud boundary, whichever comes first. Never contacts the cloud; stops before the first authenticated plan and says exactly what the operator does next. | `lzctl status` (before and after), then `lzctl intake` / `assess` / `validate` / `build` / `preflight` as the phase requires |
| `back <phase>` | **Re-enter an earlier phase deliberately.** Records who decided and why, and names what the re-entry invalidates. Undoes nothing — see "Backtracking" below. | `lzctl back <phase> --reason "..."` |
| `plan [env[,env...]\|all]` | May contact the cloud and write plan artifacts. Preflight, ordered plans, triage summary with exit-code reading. | `lzctl preflight`, `plan`, `triage` |
| `verify` | Post-apply verification, drift sweep, and (on request) the evidence bundle. | `lzctl verify`, `drift`, `report` |
| `docs` | **Local customer-document regeneration only.** No drift sweep, no cloud contact. | `lzctl docs` |
| `review` | **Hand the work to a human in the app.** Start the local UI, name the spec to load and the exact list of fields to check or fill, then stop and wait. Never contacts the cloud itself; the human may run cloud jobs from the app. | `lz-app --workspace <dir>` |

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

## Rendering: how results reach the human

The CLI emits data; the presentation is YOURS, in the transcript — there is
no terminal to look at. The facts for the progress renders come from one
read-only command:

    lzctl status --json [--workspace <dir>] [--spec <spec>] [--envs-dir <envs>] [--quick]

Its exit code is a gate like every other: **0** on track · **2** something
needs a recheck · **3** something is blocked. Never paste the raw JSON, and
never paste the CLI's plain-text form — that exists only for a human at a
prompt.

Four rules govern every render — the phase report and every verb verdict
(plan, apply, verify, validate, decisions, docs — exact goldens in
[rendering.md](rendering.md)):

1. **Verdict first.** The first line after a header answers "am I OK, and
   what now" — never context before verdict.
2. **Exceptions only.** Render what deviates; compress the healthy remainder
   to one count/list line. Error lists are the one exception to the
   exception: errors are the actionable content and are never summarized
   away (cap 20, then "and n more").
3. **One Next.** Exactly one fenced bash block per render — alternates as
   comments inside it, never a second block — always followed by the
   provenance line `runner · cloud: x · undo: y` (or log/artifact paths
   where the record is a file). Never drop `undo` — it is what stops an
   apply being read as reversible.
4. **Words only.** The whole palette: **bold** (subject, current phase,
   section labels, the deviating item), `###` verb headers, plain bullets,
   tables only for per-env verdict grids and the full-form phase table,
   fenced bash, *italics* for hints and asides, `---` only before the strip.
   No decorative symbols — tick/cross/arrow glyphs say nothing the sentence
   does not. No blockquotes. Uppercase only when quoting the gate's own
   words (DRIFT, DESTRUCTIVE, "Do NOT re-apply blindly").

And one rule of substance over style: **say what the report says.** Do not
assert a phase is complete because you just ran its command, and do not
soften a blocker into a note.

**Phases are numbered.** A phase renders as `03-build` — its zero-padded
1-based position in the `phases` array plus its name, the same shape as the
env directories (`05-network`) — everywhere a phase is named: headers,
bullets, footers, table rows, the strip. The number shows graph order (and
the shape of a re-entry: `done: 01-intake, 02-design, 05-deploy, 06-verify_post`
says phases 3 and 4 are being redone) without the reader knowing the graph.

### The strip — closes a reply that moved the engagement

A reply gets the strip when **this skill did landing-zone work in it**: ran an
`lzctl` command, edited a spec, decisions file, or env tree, reported a phase
or gate result, or answered a question about where the engagement stands. It
goes last, below everything else, even below a full report:

---
**frasers** · 03-build · 4/7 · recheck: 03-build, 04-verify_pre · next: `lzctl check regen-diff`

Slots, all from `status --json`: customer · current phase · complete/total ·
worst state (`blocked: <phases>` outranks `recheck: <phases>`; when neither
exists, `on track`) · `next:` the first command of the current phase's
`next`, name and subcommand only. One line, nothing else.

**Everything else gets no strip.** Working in this repository is not the same
as progressing an engagement: refactors, test runs, git and release work,
dependency or tooling changes, code review, documentation edits, and questions
about the pipeline's own source all end with no strip. Nor does a reply that
merely mentions a customer in passing. The test is whether a phase moved or a
gate spoke in **this** reply — if repeating the strip would print the same
line as last time because nothing happened, it is noise; drop it.

### The phase report — default form (exception-first)

Render when the phase picture changes — a phase completes, a blocker or
recheck appears or clears — and when the user asks where things stand.
Routine turns get the strip alone; a verb that ran this turn gets its card
(rendering.md) plus the strip.

**FRASERS** — 03-build · 4/7 complete · 13 envs

**Needs attention**
- **03-build** — the spec is newer than 9 of 13 envs; timestamp hint only, `lzctl check regen-diff` proves it
- **04-verify_pre** — re-plan after the tree is regenerated; planning from a stale tree is a forbidden transition

**Next**
```bash
lzctl check regen-diff --envs-dir huawei-lz/envs-frasers --spec lz_spec/lz.spec.frasers.json
lzctl build ...   # only if regen-diff reports differences
```
agent · cloud: none · undo: regenerate or delete the tree

done: 01-intake, 02-design, 05-deploy, 06-verify_post · pending: 07-deliver

Slot rules — omission-driven, everything from the JSON:

- **Header**: customer — numbered current phase · complete/total · env count. The
  `spec`/`envs` paths belong to the full form only.
- **Needs attention**: one bold-led bullet per phase whose status is
  `recheck` or `blocked`, in graph order with `blocked` first, each in the
  gate's own words (`blockers`, else `notes`). All clear: the section is
  the single line `On track — nothing needs attention.`
- **Needs from you**: when the current phase has `needs`, a bold-labelled
  line naming what a person must supply. Omitted when empty.
- **Next**: the current phase's `next` commands, one fenced block (rule 3),
  provenance line after.
- *Journal*: while a re-entry's invalidated phases are incomplete, one
  italic line under the header — *re-entered design 2026-09-01 (tester):
  supernet moved*. Omitted otherwise.
- *Hints* (`hints`, e.g. "Timestamp hint only. Content may still match.")
  render italic above the footer. Omitted when empty.
- **Footer**: `done: <phases> · pending: <phases>` — the compressed healthy
  remainder. A phase already under Needs attention never repeats here.

The **full form** — the complete seven-row phase table, a card per live
phase, the journal — renders on explicit ask only ("full status", `-v`);
its golden is in [rendering.md](rendering.md).

**Staleness is derived**: edit the spec and the tree reports `recheck` on its
own, whether or not anyone declared it — which is how "plan or apply from a
stale tree" gets caught rather than remembered. `recheck` is a prompt to
verify, not a verdict: `lzctl check regen-diff` settles it either way.

## Backtracking

Going back is normal — a customer changes an answer, a workshop moves a CIDR.

    lzctl back design --reason "customer moved the prod supernet after the IP workshop"

It is a **re-entry, never an undo.** It deletes nothing and touches no cloud
resource; it records who decided and why in `lz.spec.<customer>.journal.jsonl`
(shown by `status`, collected into the evidence bundle), and names the phases
that must be redone in order. The staleness that follows is derived from the
files themselves, so the journal only has to carry the part a machine cannot
infer: the reason.

Two hard rules:

1. **Backtracking past an apply changes the configuration, not the estate.**
   Applied resources stay applied. The next plan diffs your new configuration
   against live infrastructure, so read it as a change to production — a row
   removed from the spec plans a **destroy**. `back` says this out loud when
   apply logs exist.
2. **Undoing deployed infrastructure is never a phase operation.** It is
   Terraform under a human's typed confirmation, or state surgery — see
   assets/state-surgery and assets/plan-triage-drift. No skill action does it.

## The app — where humans verify and fill gaps

`lz-app` is the human half of the contract: a local, loopback-only UI over the
same spec, the same validator, and the same `lzctl` jobs. Route every decision
that belongs to a person through it instead of asking them to hand-edit
generated JSON or read a plan out of a terminal.

    lz-app --workspace <workspace>            # http://127.0.0.1:8600
    lz-app --port 8611 --no-browser           # if 8600 is taken / headless

It is a server: start it in the BACKGROUND or hand the operator the command —
never block the session waiting on it. Bind loopback only; a non-loopback bind
serves the CSRF token to anyone who can reach the page.

| The human needs to… | In the app | Agent's part |
|---|---|---|
| resolve an OPEN decision or fill a gap | **Decisions & gaps** (top of the rail): resolution + who decided + why; each gap deep-links to its sheet | register gaps with `lzctl gap add`, then stop |
| review a draft spec and fill gap values | spec dropdown, then **Load**, edit sheets, **Validate**, **Save** | name the spec and list the exact fields/sentinels to fill, then stop |
| confirm a design before it is built | sheet-by-sheet read, MANDATORY / OPTIONAL-billable / AUTO / RESERVED badges | point at the sheets your interpretation touched |
| see what a change would do | **Plan** job (env picker, dependency order, triage + cost summary) | say which envs and what you expect |
| apply | **Apply** job — dry-run by default, warning box + typed confirmation, destructive plans blocked by triage | never run it; present it |
| check live drift / hand over | **Drift**, **Export artifact** | interpret the report afterwards |

After a human saves in the app, **re-read the spec from disk** — it is now the
source of truth and any in-memory copy is stale. Their edits are reviewable as
a spec diff.

## Companion skill (optional)

The `huawei-cloud-terraform-generator` skill (separate distribution, not included in this repository) generates single-service resources with per-service references and region-availability verification. It is optional — this skill and the pipeline are fully usable without it; without it, author single-resource HCL from the provider docs per the evidence hierarchy below.

It matters only for work OUTSIDE the module catalogue: hand-maintained
workload modules, day-2 single-service additions, debugging one resource's
HCL. The landing-zone workflow itself never needs it — generated envs come
from deterministic codegen, and agents never author `resource` blocks (the
pre-apply guard enforces this). It is distributed through the Huawei Cloud
Skills portal:
<https://skills.huaweicloud.com/detail/huawei-cloud-terraform-generator> —
install per the portal's instructions (the skill folder lands in the agent's
skills directory, e.g. `.claude/skills/huawei-cloud-terraform-generator/`).
Do not install it for validation runs of THIS skill — its broad trigger
description can capture routine infrastructure requests that belong here.

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
| design | draft spec + decisions files | OPEN items resolved; every `REPLACE_WITH_` gap filled by a human in the app; validation passes with 0 errors | build with unresolved OPEN decisions (`lzctl build` exits 3), or with a placeholder still in the spec |
| build | spec validating with 0 errors | generated envs + fresh deps.json | plan/apply from a stale tree |
| verify_pre | built tree | clean plan triage + passing harness | apply with untriaged destructive changes |
| deploy | reviewed plan + approvals (typed confirm for destructive) | applied envs in dependency order + state backups + run logs | applying out of dependency order |
| verify_post | applied infrastructure | every env clean or known-benign | deliver without verification |
| deliver | verified infrastructure | evidence bundle + generated docs + handover artifact | handover without verification evidence |

No phase may be skipped forward. A workflow may stop at any GATE, but an interrupted deployment can leave a partially applied deployment and must be resumed through verify_post (`lzctl verify`) before further changes.

The same phase graph is machine-readable at `schemas/phases.json`; skill, CLI docs, and eval fixtures share it.
