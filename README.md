# Huawei Cloud Landing Zone Pipeline

> A config-driven pipeline and agent skill that turn one reviewed specification into a complete, governed Huawei Cloud landing zone — deterministically, with explicit approval gates for high-impact actions.

**The contract: the skill decides and asks; the pipeline executes and gates.** Judgment lives in reviewable artifacts, every gate is an exit code, and no deployable value is generated without an explicit decision — see [docs/skill-pipeline-contract.md](docs/skill-pipeline-contract.md).

License: Apache-2.0.

## Why this exists

Manual landing-zone delivery can take weeks of console work: dozens of accounts, OUs, SCPs, VPCs, router attachments, trackers, and buckets, each configured by hand and difficult to reproduce consistently. This repo replaces that with a spec-driven flow:

- **One authoritative input.** A JSON spec (`lz.spec.<customer>.json`) is the single configuration store. The Excel workbook customers see is a *generated artifact* of that spec, never an input.
- **Deterministic generation.** For a fixed generator, schema, module snapshot, and input spec, generation is byte-identical (`terraform.tfvars.json`, `*.generated.tf`) — enforced by a regression harness, not by convention.
- **Handover-safe output.** The generated Terraform is plain, readable HCL. A customer who receives only the Terraform tree and the runner can operate it without the pipeline, the skill, or any AI.

## What it deploys

The reference implementation composes 12 ordered Terraform environments across the 9 governance domains of the Cloud Adoption Framework, using 15 modules (`terraform/modules/`). Other landing zones may enable fewer domains or different compositions — the spec decides:

| Domain | Env(s) | Covers |
|---|---|---|
| Organization & accounts | `01-foundation` | Org, OUs, accounts, Identity Center instance, tag policies |
| Finance | `02-finance` | Cost-center enterprise projects, tag dictionary |
| Identity | `03-identity` | Identity Center users/groups/permission sets, per-account IAM baseline |
| Perimeter | `04-perimeter` | SCP guardrails (v5 syntax), predefined tags, Config conformance |
| Network | `05-network`, `09-network-cfw` | Enterprise Router hub-and-spoke, NAT, ELB, flow logs, Cloud Firewall rule plane |
| Observability | `06-observability` | Org CTS tracker, audit/log buckets, KMS, log aggregation, CES/SMN |
| Security | `07-security` | SecMaster workspace |
| DNS | `08-network-dns` | Public/private zones, hybrid resolver |
| VPN & workload isolation | `10-network-vpn`, `11-network-sgacl` | Site-to-cloud VPN, workload security groups |

(`00-bootstrap` creates the OBS state bucket first.)

## Architecture

```text
user requirements
      |
      v
+--------------------------------------+
| Landing Zone skill                   |   domain knowledge + decision logic
| skills/huawei-cloud-landing-zone/    |   (the model reasons WITH it)
+--------------------------------------+
      |  assessment / design / validation artifacts
      v
+--------------------------------------+
| lzctl - deterministic pipeline       |   intake > assess > validate > build
| pipeline/lz_pipeline/lzctl.py        |   > preflight > plan > apply > verify
+--------------------------------------+
      |  terraform.tfvars.json + *.generated.tf + deps.json
      v
+--------------------------------------+
| Terraform                            |   12 plain-HCL environments composed from
| generated envs + module snapshot     |   15 versioned domain modules
+--------------------------------------+
      |
      v
  Huawei Cloud  -->  lzctl verify / lzctl report (evidence bundle)
```

The model reasons and interprets; the skill provides workflow and design rules; the pipeline provides deterministic orchestration; validators enforce correctness; Terraform executes; the human approves. Critical deterministic logic never lives in the model; the same pipeline works with any model or none — a human can run every command.

| Component | Responsibility | Reasons? | Executes infrastructure? |
|---|---|---|---|
| Model (any LLM, or a human) | Interpretation and planning | yes | no |
| Skill (`skills/huawei-cloud-landing-zone/`) | Domain workflow + design rules | guides reasoning | no direct execution |
| Pipeline (`lzctl`) | Deterministic orchestration | no | yes |
| Terraform | Infrastructure execution | no | yes |
| Validators (JSON Schema, platform rules, plan triage) | Enforcement | no — deterministic | no |
| Human | Approval at gates | yes | destructive applies require a second typed confirmation, which `--yes` never bypasses |

An optional companion skill, [`huawei-cloud-terraform-generator`](https://skills.huaweicloud.com/detail/huawei-cloud-terraform-generator) (separate distribution: `npx clawhub install @huaweiclouddev/huawei-cloud-terraform-generator`), generates single-service HCL with per-service references — useful for day-2 workload modules outside the module catalogue. The landing-zone workflow never needs it: generated envs come from deterministic codegen, and agents never author `resource` blocks.

## How the skill and pipeline work together

The skill decides and asks; the pipeline executes. Example: an agent runs `lzctl assess` (which deterministically classifies every questionnaire answer as ANSWERED / DEFAULTED / OPEN — it never guesses, and its draft spec starts *neutral*: every value unset, failing validation until interpreted), then the agent interprets the *prose* answers into the draft using the skill's design rules, then `lzctl validate` gates the result mechanically — and `lzctl build` refuses to run while `lz.spec.<customer>.decisions.json` still holds OPEN items without a recorded resolution. Every step the agent takes is a command a human could have typed; every judgment call is written into an artifact (the decisions files, the spec diff) a human reviews and signs off.

## Which models can be used

The execution boundary is model-independent by design: all model-facing surfaces are files and CLIs, so no step depends on a particular model's behavior to be safe. Whether a given model performs the judgment steps *well* is a separate, measured question — see `tests/evaluation/` for the harness and current results per model. The spec is validated by a generated JSON Schema (`schemas/lz.spec.schema.json`), the questionnaire dump is plain JSON, and every gate is an exit code. It is also fully usable with **no** model: run the commands below by hand and edit the spec in the bundled editor (`app/`, see `app/USER-GUIDE.md`).

Where the Claude coupling actually lives, so the claim is checkable: the pipeline, app, schemas, and Terraform contain none. The skills are *packaged* for Claude Code (`SKILL.md` format, `.claude/skills/`, the plugin manifests), but their content is plain markdown whose instructions are all "run this command, read this exit code" — any agent framework can consume them as a system prompt, and a human can follow them directly. The measurement tooling currently drives models through the Claude Code CLI: the eval harness takes other providers via its adapter registry (`tests/evaluation/adapter.py` — adding a provider = adding a function), while the E2E benchmark (`tests/evaluation/e2e_bench/`) specifically measures the model × skills × Claude Code combination and would need its own runner hook for a different agent CLI.

## Prerequisites

- Python ≥ 3.10 with `openpyxl` (the only Python dependency)
- Terraform ≥ 1.6.3 on PATH (only for plan/apply/verify — spec work needs none)
- Huawei Cloud credentials — needed only at deploy time, via environment variables (see `docs/configuration.md`); never stored in the repo or the spec

## Install

The standard installation model:

```bash
pip install .        # normal use  (gives you the lzctl and lz-app commands)
pip install -e .     # development (editable)
```

Plain-checkout execution (no install) is a development/CI mode — see
`docs/development.md`.

### Installing just the skills

The agent skills install independently of the pipeline:

```bash
# 1. One-liner — skills CLI (installs every skill in the repo; -g = user-level, -y = no prompts)
npx skills add Nigelleong314/huawei-cloud-landing-zone-pipeline -g -y

# ...or one skill only:
npx skills add Nigelleong314/huawei-cloud-landing-zone-pipeline@huawei-cloud-landing-zone -g -y
```

Update later with `npx skills check` / `npx skills update`.

```bash
# 2. Claude Code plugin marketplace (enables auto-update from /plugin)
/plugin marketplace add Nigelleong314/huawei-cloud-landing-zone-pipeline
/plugin install huawei-cloud-landing-zone-pipeline@huawei-cloud-landing-zone-pipeline
```

```bash
# 3. Manual copy — per-project (a git clone is the only prerequisite)
mkdir -p <workspace>/.claude/skills
cp -r skills/huawei-cloud-landing-zone skills/questionnaire-to-spec <workspace>/.claude/skills/

# ...or user-level (available in every project):
cp -r skills/huawei-cloud-landing-zone skills/questionnaire-to-spec ~/.claude/skills/
```

The skills assume `lzctl` is installed (`pip install .` above) and that
`terraform/scaffold` + `terraform/modules` are reachable in the workspace —
see **Package boundary** below.

### Using the skills conversationally

With the skills installed, a Claude Code session in the workspace drives the
whole workflow through `lzctl` from plain conversation — describing the goal
is enough to trigger them ("here's the filled questionnaire for acme, take it
to a validated spec"), and explicit commands exist for precision:

```text
/questionnaire-to-spec acme-filled.xlsx customer=acme
/huawei-cloud-landing-zone advance          # local generation up to the next gate
```

`status` (read-only), `advance`, `plan`, `verify`, and `docs` are the full
action set — the complete grammar, qualifier allowlist, and scope of each
action live in one place:
[skills/huawei-cloud-landing-zone/SKILL.md](skills/huawei-cloud-landing-zone/SKILL.md)
(§ Invocation).

**These skills never execute `terraform apply`.** They stop at the apply gate
and present the operator command — the typed destructive confirmation is
always a human at a terminal.

**Package boundary**: the wheel provides the pipeline *runtime* — every
command, schema, template, and fixture needed to intake, assess, validate,
and generate. The Terraform assets (`terraform/modules/`,
`terraform/scaffold/`) are repository/handover assets, referenced by path
(`--scaffold-dir`), not packaged — deploying needs a checkout or a handover
artifact alongside the installed package.

## Quickstart

```bash
# 1. Generate the assessment questionnaire; send it to the customer
python -m lz_pipeline.tools.gen_questionnaire -o questionnaire.xlsx

# 2. Customer fills it in and returns it

# 3. Mechanical extraction (no interpretation)
lzctl intake filled-questionnaire.xlsx -o dump.json

# 4. Deterministic assessment: NEUTRAL draft (every value unset) + decisions
#    files (never guesses). The draft fails validation until interpreted.
lzctl assess dump.json --customer acme --workspace .
#    -> specs/lz.spec.acme.json (neutral draft)
#       specs/lz.spec.acme.decisions.md (human agenda)
#       specs/lz.spec.acme.decisions.json (build gate: OPEN items block build)

# 5. Interpret the answered questions into the draft spec, and record a
#    resolution for every OPEN item in the decisions .json
#    (an agent using skills/questionnaire-to-spec, or an engineer by hand)

# 6. Gate the spec (schema + semantic + platform rules)
lzctl validate specs/lz.spec.acme.json

# 7. Generate the Terraform inputs
lzctl build --spec specs/lz.spec.acme.json --envs-dir envs --scaffold-dir terraform/scaffold

# 8. Deploy (each step gated; envs run in deps.json dependency order)
lzctl preflight --envs-dir envs
lzctl plan      --envs-dir envs --all
lzctl apply     --envs-dir envs --all        # confirm per env; state backup first

# 9. Prove it
lzctl verify    --envs-dir envs              # every env clean or known-benign
lzctl report    --envs-dir envs              # evidence bundle -> envs/evidence/<ts>/
```

Note: `validate`, `build`, `check`, and `export` delegate to the installed pipeline modules and run in **your** working directory — relative paths resolve exactly as typed, the same as every other command.

## Dry runs and plan-only use

- `lzctl plan --envs-dir <envs> --all` plans everything, writes `tf.plan` per env, triages it, and never applies. Exit code 0 clean / 2 changes / 3 destructive changes.
- `--dry-run` on `plan`, `apply`, and `state-backup` prints the exact commands without any cloud access.
- `lzctl triage plan1.json ...` classifies already-exported plan JSON offline.
- `lzctl apply` reuses the reviewed `tf.plan` when configuration is unchanged since the plan run (approve-what-you-apply); Terraform itself refuses the file if state moved.

## Development

```bash
pytest                              # unit tier (default)
python -m lz_spec.verify_pipeline   # full regression harness (7 checks) — also `lzctl check`
```

Running from a checkout, the integration/eval test tiers, adding another model, extending the skill: `docs/development.md`. Test details: `docs/testing.md`.

## Out of scope

- Workload/application infrastructure (the LZ hands over accounts, network, and guardrails; workloads are yours)
- Direct Connect / Cloud Connect physical provisioning
- SecMaster deployment guidance (module ships; operational guidance pending)
- Replacing Huawei Resource Governance Center — see `docs/rgc-positioning.md`
- Multi-cloud

## More documentation

| Doc | Contents |
|---|---|
| `docs/skill-pipeline-contract.md` | The product's core design statement: skill decides, pipeline gates |
| `docs/architecture.md` | Two-layer design, package map, artifact flow, module snapshot story |
| `docs/development.md` | Checkout mode, test tiers, adding a model, extending the skill |
| `docs/workflow.md` | Phase contract, every `lzctl` command with flags and exit codes, gates, failure handling |
| `docs/configuration.md` | Every environment variable, workspace layout, profiles, rate cards, schema |
| `docs/testing.md` | Test suites, the verify harness, the leak guard, the eval suite |
| `docs/rgc-positioning.md` | RGC vs this pipeline, coexistence guidance |
| `docs/troubleshooting.md` | Known errors with exact signatures and fixes |
| `app/USER-GUIDE.md` | The bundled spec editor / job runner |
