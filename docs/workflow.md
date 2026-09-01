# Workflow

## Phase contract

The authoritative phase graph lives in `schemas/phases.json`; this table renders it.

| Phase | Entry artifact | Commands | Exit artifact |
|---|---|---|---|
| **intake** | filled `questionnaire.xlsx` | `lzctl intake`, `lzctl assess` | `dump.json`; neutral draft `specs/lz.spec.<customer>.json`; `…decisions.md` + `…decisions.json` |
| **design** | draft spec + decisions files | edit/interpret (agent or engineer), resolve OPEN items, `lzctl validate` | validated `lz.spec.<customer>.json` (0 errors), no unresolved OPEN decisions |
| **build** | validated spec | `lzctl build` (exits 3 on unresolved OPEN decisions) | generated envs (tfvars + `*.generated.tf`), fresh `deps.json` |
| **verify_pre** | built tree | `lzctl preflight`, `lzctl plan`, `lzctl triage`, `lzctl check` | clean plan triage, passing harness |
| **deploy** | reviewed plan + approvals | `lzctl apply` (typed confirm for destructive) | applied envs in dependency order, `state-backups/`, `lzctl-logs/` |
| **verify_post** | applied infrastructure | `lzctl verify`, `lzctl drift` | every env clean or known-benign; optional drift report |
| **deliver** | verified infrastructure | `lzctl docs`, `lzctl report`, `lzctl export` | doc set (xlsx), `evidence/<ts>/` bundle, handover artifact |

A phase does not start until the previous phase's exit artifact exists and its gate passed.

## The commands

Exit codes follow Terraform's plan convention where relevant: **0** ok / no changes, **1** error, **2** changes present (or stopped/needs attention), **3** destructive changes present.

### `lzctl status [--workspace DIR] [--spec SPEC] [--envs-dir <envs>] [--json] [-v] [--quick]`

Where the workspace sits on the phase graph. Completely read-only.

`--json` is the contract: every phase with its state, plain-English status (`complete` / `recheck` / `blocked` / `pending`), gist, exit artifacts, blockers, notes, needs, the next command(s), and the runner / cloud-access / undo triple — plus the re-entry journal. **Callers format it; this command does not paint a terminal UI.** The agent renders it into its own reply in two forms — a one-line strip closing every working reply, and an exception-first report when the phase picture changes (goldens in the huawei-cloud-landing-zone skill: SKILL.md "Rendering" + rendering.md); the plain-text form exists only for a human at a prompt.

Every phase's state is **derived from artifacts**, never from a stored pointer: the spec and its decisions file, `<env>/terraform.tfvars.json` + `deps.json`, `<env>/tf.plan`, `lzctl-logs/*-{plan,apply,drift}.log`, `state-backups/`, `evidence/`. A phase reports `recheck` on its own the moment its inputs change (edit the spec → the tree needs a recheck → so do the plans), and an interrupted apply (`.lzctl.lock`) reports `blocked` with the recovery procedure. Timestamps only *suggest* a mismatch — `lzctl check regen-diff` proves it. `--quick` skips the validator subprocess and says so. Exit **0** on track, **2** something needs a recheck, **3** something is blocked.

### `lzctl back PHASE --reason "why" [--by WHO] [--workspace DIR] [--spec SPEC]`

Deliberate re-entry of an earlier phase. Appends `{at, by, from_phase, phase, reason, invalidates}` to `specs/lz.spec.<customer>.journal.jsonl` (shown by `status`) and prints the phases that must be redone in order.

**It undoes nothing** — no file is deleted and no cloud resource is touched; staleness is derived from the files themselves, so the journal carries only what a machine cannot infer: the reason and who decided. When apply logs exist it warns that the estate stays applied and that the next plan diffs the new configuration against live infrastructure — a row removed from the spec plans a destroy. Undoing deployed infrastructure is Terraform under a human's typed confirmation, or state surgery; never a phase operation. Exit 0, 1 if the target is not earlier than the current phase, 2 on an unknown phase.

### `lzctl preflight --envs-dir <envs>`

Checks: terraform on PATH and ≥ 1.6.3; `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` set; `AWS_REQUEST_CHECKSUM_CALCULATION` and `AWS_RESPONSE_CHECKSUM_VALIDATION` both `when_required` (or state save fails *after* apply); envs dir and `deps.json` present. Exit 0 all passed, 1 otherwise.

### `lzctl order --envs-dir <envs>`

Prints the apply order from `deps.json` (falls back to numeric prefix order). Exit 0.

### `lzctl plan --envs-dir <envs> [ENV[,ENV...] | --all] [--dry-run] [--pricing CARD.json]`

Per selected env (selection accepts exact names or unique prefixes, always runs in apply order): `terraform init` if needed (with `-backend-config=backend.hcl` when present), `terraform plan -out tf.plan -detailed-exitcode`, then triage + a monthly cost estimate (the report always names the rate card's region). Exit: worst of 0 / 2 / 3 across envs; 1 on plan error (stops immediately).

### `lzctl triage PLAN_JSON [...]`

Offline classification of exported plan JSON (`terraform show -json tf.plan > plan.json`) into benign / create / update / destructive classes. Same 0/2/3 convention.

### `lzctl apply --envs-dir <envs> [ENV[,ENV...] | --all] [--dry-run] [--allow-destroy] [--yes] [--destroy-confirm ENV]...`

Per env, in order:

1. **Lock** — advisory `.lzctl.lock` (one apply at a time on this machine; stale after 2 h).
2. **State backup** — `terraform state pull` → `state-backups/<ts>-<env>.tfstate.json`, always, before anything else.
3. **Plan + triage gate** — reuses the saved `tf.plan` if configuration is unchanged since the plan run; otherwise re-plans. No changes → skip. Destructive changes → **blocked (exit 3)** unless `--allow-destroy`.
4. **Interactive confirm** — `apply <env>? [y/N]`; skipped by `--yes`.
5. **Destructive second confirm** — if the plan is destructive, a second, explicit confirmation: type the env name. `--yes` **never** satisfies this. For CI, pre-authorize one exact env with `--destroy-confirm <env>` (repeatable).
6. **Apply** the reviewed plan file.
7. **Retry-once on documented transients** — if the apply fails and the output matches a transient signature (`LTS.2101,EPS.0004` by default; extend via the `LZ_TRANSIENT_SIGNATURES` env var), re-plan + apply the remainder exactly once. Never a replay of the stale plan.

Exit: 0 applied/current, 1 apply or plan error, 2 stopped by operator, 3 blocked on destructive changes or a content gate (placeholder PSK), 4 refused: this context cannot satisfy a required confirmation (agent session without `LZ_OPERATOR_APPLY=1`, or an interactive prompt with no terminal).

### `lzctl drift --envs-dir <envs> [ENV[,ENV...]] [--report out.md]`

Re-plans every (or the selected) env and summarizes: `clean`, `known-benign drift only`, `DRIFT: n destructive, n update, n create`, `ERROR`, or `SKIP (not initialized)`. Optional markdown report. Exit 0 clean/benign, 2 if any drift or errors.

### `lzctl verify --envs-dir <envs> [ENV[,ENV...]] [--report out.md]`

The post-apply gate: runs the drift sweep and passes only if **every env is clean or known-benign**. Exit 0 pass, 2 fail (the deployed infrastructure is inconsistent — investigate before further changes).

### `lzctl report --envs-dir <envs> [--out DIR] [--last-logs N]`

Evidence bundle → `<envs>/evidence/<ts>/` (or `--out`): the last N run logs (default 10), `deps.json`, a fresh `drift-report.md`, `versions.txt`, and a sha256 `MANIFEST.txt` over the bundle. Exit 0 if drift clean/benign, 2 otherwise.

### `lzctl state-backup --envs-dir <envs> [ENV | --all] [--dry-run]`

On-demand `terraform state pull` backups to `state-backups/`. Exit 0.

### `lzctl adopt --envs-dir <envs> ENV ADDRESS CLOUD_ID [--dry-run]`

`terraform import` an existing cloud resource, then re-plan. Exit 0 imported clean, 1 import failed, 2 imported but the configuration still differs (align and re-plan).

### `lzctl who-changed RESOURCE_NAME`

Prints the CTS lookup procedure for auditing who changed a resource. Exit 0.

### `lzctl docs --envs-dir <envs> --out-dir DIR [--states-dir DIR] [--customer NAME] [--spec SPEC.json]`

Regenerates the customer doc set from the tree: IP management workbook, config book, resource checklist (needs `--states-dir`), and — with `--spec` — the Excel LLD workbook (a generated artifact of the spec). Exit 0 all generated.

### `lzctl intake XLSX [-o OUT.json]`

Filled questionnaire → mechanical answers dump. No interpretation. Exit code from the dump tool.

### `lzctl assess DUMP.json --customer SLUG [--workspace DIR] [--force]`

Deterministic assessment pre-pass: writes a schema-shaped **neutral** draft (`specs/lz.spec.<customer>.json`, every deployable sheet value unset — it intentionally fails validation until customer answers and approved defaults are interpreted into it) plus two decisions files: `…decisions.md` (human agenda) and `…decisions.json` (machine-readable; the build gate). Every question lands in exactly one state — ANSWERED (interpret into the draft), DEFAULTED (silent with a documented default; review), or OPEN (required, no default; blocks build until a complete resolution — status + approved_by + reason — is recorded; contract in `schemas/decisions.schema.json`). The draft carries a `provenance` block (decisions filename, assessment id, and a hash of the immutable decision set), so the gate follows the spec through copies and renames, and truncating or altering the manifest blocks build just like an unresolved item. **Detaching lineage** — converting a questionnaire-derived spec to a manually managed baseline — is done by deleting the `provenance` block: a deliberate edit that any spec review will see. An audited `lzctl detach-lineage` command (recording who/why) is planned. This command never guesses. Refuses to overwrite an existing draft without `--force`. Exit 0.

### Delegated commands: `build`, `validate` (alias `spec-validate`), `check`

These need the installed pipeline (a runtime-only handover installation says so and exits 2). Arguments pass through:

```bash
lzctl validate <spec.json>                       # -> python -m lz_pipeline spec-validate
lzctl build --spec <spec> --envs-dir <envs> [--scaffold-dir <dir>] [--only 05,06]
# (--ir is an accepted alias for --spec on build and docs)
lzctl check [all|regen-diff|validate|template-check|rules|deps|fmt|unit] \
            [--envs-dir <envs>] [--spec <spec>]   # -> python -m lz_spec.verify_pipeline
lzctl deps --envs-dir <envs>                      # regenerate deps.json (build writes it too)
```

Delegated commands preserve the caller's working directory — relative paths resolve exactly as supplied (locked by `tests/unit/test_cli_contract.py`).

## Approval gates, summarized

1. **Spec gate** — `lzctl validate` must report 0 errors before build.
2. **Plan gate** — every apply happens from a triaged, reviewed plan file.
3. **Interactive confirm** — per env; `--yes` skips only this one.
4. **Destructive double-gate** — exit-3 plans are blocked without `--allow-destroy`, and even then require typing the env name (or an exact `--destroy-confirm <env>` in CI). No flag combination silently destroys.
5. **Verify gate** — the engagement is not done until `lzctl verify` returns 0.

## Failure handling

- **Mid-chain stop.** A plan or apply error stops the chain immediately with `FAILED (... in <env>; earlier envs were applied)`. Fix the env, re-run; clean envs are skipped.
- **Retry-once.** Only outputs matching documented transient signatures are retried, exactly once, via re-plan + apply (a partial apply makes the saved plan stale, so replaying it would be wrong). Keep signatures *specific* — a broad match retries real failures.
- **Stale plan.** If Terraform refuses the saved plan (`stale` in the output), re-run `plan` for that env, review, and apply again.
- **State restore is manual.** The backup taken before the apply sits in `state-backups/`; restoring means deliberately following the "recovering from a failed apply" cookbook (skill asset `apply-orchestration`), never an automatic push.
- **Locks.** A held `.lzctl.lock` names its holder; remove it only if that run is dead. Stale locks (> 2 h) are broken automatically with a note.
