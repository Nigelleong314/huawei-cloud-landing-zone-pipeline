# CI/CD plan for the Terraform output

**Scope:** running the generated envs (the customer artifact: `envs/` + `modules/` +
`runner/`) through CI/CD. Written to be platform-neutral (maps 1:1 onto GitHub
Actions or GitLab CI); draft your YAML against the stage tables below and the
command column is what each job runs. Everything a job executes already exists
in the artifact — CI adds orchestration, credentials, and gates, never logic.

## Ground rules the YAML must encode

| Rule | Consequence in CI |
|---|---|
| No native state locking (LZR-007) | ONE apply pipeline at a time, org-wide: a single concurrency group (e.g. `lz-apply`), `cancel-in-progress: false`. lzctl's advisory lock protects a runner host, not the org — CI concurrency is the real serializer. |
| Strict env ordering (LZR-008) | Apply/plan jobs run sequentially in `runner/lzctl.py order` sequence (drive from `envs/deps.json`; never hardcode the list in YAML). |
| Checksum env vars (LZR-005) | Every terraform job sets the 4 vars; `lzctl preflight` is stage 0 and fails fast if the runner image forgot them. |
| Destructive changes (LZR-012/019) | `plan_triage.py` exit codes gate: 0 pass, 2 pass-with-changes, 3 fail unless the run carries an explicit allow-destroy approval. |
| Known transients (LZR-018) | Apply steps get retry: 1 (LTS.2101, EP propagation, new-agency 403). |
| Credentials | Never in the repo. v1: environment-scoped secrets (master AK/SK) exposed only to protected environments with required reviewers. Target state (PRD): OIDC federation → temporary 30-min AK/SK minted per run; agent/PR jobs get NO credentials at all. |

## Pipeline A — PR validation (trigger: pull_request; no credentials except stage 4)

| # | Stage | Command | Gate |
|---|---|---|---|
| 1 | structure | `py runner/lzctl.py order --envs-dir envs` + assert `deps.json` present and env dirs match | fail = malformed artifact |
| 2 | fmt + validate | matrix over envs: `terraform fmt -check` then `terraform init -backend=false` + `terraform validate` | hard gate; needs no creds (use a plugin cache image layer) |
| 3 | policy | `conftest test --policy policies/ envs/*/terraform.tfvars.json` (OPA rego) | hard gate where policies ship; optional otherwise |
| 4 | plan + triage (optional but recommended) | per env in order: `terraform init -backend-config=backend.hcl`, `terraform plan -out tf.plan`, `terraform show -json tf.plan > plan.json`, `py runner/plan_triage.py plan.json` | exit 3 fails unless PR carries the `allow-destroy` label; triage report posted as PR comment + plan.json uploaded as artifact |

Stage 4 is the only credentialed PR stage — put it behind a protected
environment (`plan-readonly`) or drop it for untrusted forks.

## Pipeline B — Apply (trigger: merge to main, or manual dispatch; concurrency group `lz-apply`)

| # | Stage | Command | Gate |
|---|---|---|---|
| 1 | preflight | `py runner/lzctl.py preflight --envs-dir envs` | fail fast on env/tooling problems |
| 2 | plan-all | per env in `deps.json` order: plan + `show -json` + triage; upload every `tf.plan` + triage output as ONE artifact bundle | exit 3 stops here unless dispatch input `allow_destroy=true` |
| 3 | **approval** | — | environment protection with required reviewer(s). This is the email-approval gate from PRD §10 in CI form; the triage summary is the thing the approver reads. |
| 4 | apply | per env sequentially: `state pull` backup (upload as artifact), `terraform apply tf.plan` (the SAME plan file from stage 2 — what was approved is what applies), retry once on known transients | any failure stops the chain (later envs never run); state backup artifact retained |
| 5 | post-verify | re-plan all envs, triage must report clean or known-benign only | fail = apply left drift; investigate before anything else runs |

Notes for the YAML:
- Stage 2 and 4 must run on the same artifact bundle: approve-what-you-apply.
  If the plan is stale (state changed between plan and apply), terraform
  refuses the saved plan — that is the desired behaviour, re-run the pipeline.
- Model each env as a matrix element with `max-parallel: 1` (or chained jobs)
  — parallel applies are forbidden by LZR-007 even across envs.
- `07-security`-class paid features: gate with a dispatch input if you want a
  second explicit approval for cost-bearing envs.

## Pipeline C — Drift sentinel (trigger: schedule, e.g. daily; read-only creds)

| # | Stage | Command | Outcome |
|---|---|---|---|
| 1 | drift | `py runner/lzctl.py drift --envs-dir envs --report drift-report.md` | exit 0 = clean/benign: upload report, done. exit 2 = open an issue / send SMN-email with the report; do NOT auto-apply. |

## Pipeline D — delivery side (the pipeline workspace repo, not the artifact)

| # | Stage | Command | Gate |
|---|---|---|---|
| 1 | verify (on PR) | `py lz_spec/verify_pipeline.py` | the full regression suite (goldens are the byte-identical gate) |
| 2 | release (on tag) | `py -m lz_pipeline.export_v2 --profile lz_pipeline/profiles/<customer>.json --target dist/ --version <tag>` then zip + attach | export is deterministic; CHANGELOG.md generated from the spec-IR diff |

## Stage/gate count summary

- **PR:** 4 stages, 3 hard gates (validate, policy, triage-destructive).
- **Apply:** 5 stages, 3 gates (preflight, human approval, destructive stop) +
  the org-wide concurrency serialization.
- **Drift:** 1 scheduled stage, alert-only.
- **Release (delivery side):** 2 stages, 1 gate (regression suite).

## Mapping cheat-sheet for your YAML draft

| YAML concept | Use |
|---|---|
| `concurrency:` | `lz-apply`, cancel-in-progress false (Pipeline B); `lz-plan-${{ PR }}` for A4 |
| `environment:` + required reviewers | stage B3 approval; also scopes the AK/SK secrets |
| job matrix | env list — generate from `deps.json` (`lzctl order`), don't hardcode |
| artifacts | `tf.plan` files + triage JSON (B2→B4), state backups (B4), drift report (C) |
| `workflow_dispatch` inputs | `allow_destroy: boolean`, `only_env: string` (maps to `lzctl apply <env>`) |
| retry / continue-on-error | retry once on apply (LZR-018); never continue-on-error on apply jobs |
| schedule | Pipeline C cron |

Draft your YAML against this; send it over and I'll map each job/step back to
the exact runner/pipeline commands and flag anything that violates the ground
rules.
