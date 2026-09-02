# Changelog

## Unreleased

### Added

- **`null` is the declared unknown**: every typed slot accepts null for "not known yet"; `lzctl set` writes one value at a schema-validated path (`--value` typed coercion, `--json`, `--null`), and `lzctl set --field 'Sheet.Table[+]' --json '{...}'` appends a row with every column checked against the schema — the last spec write that used to need a hand-rolled JSON mutator. **LZR-034** errors on an unset required scalar no OPEN decision tracks; **LZR-035** errors on an ANSWERED decision whose target holds nothing — unless a registered OPEN gap covers the target (the answer settled intent; the concrete values are owed and block build); **LZR-036** errors on an enabled network plane with no VPCs. Validation at 0 errors with OPEN gaps outstanding is now a legitimate, reachable state; `lzctl build` still exits 3 until every OPEN item carries a resolution.

- **Decisions gate reaches the UI**: the app's **Decisions & gaps** view resolves OPEN decisions and fills gap values (resolution + who decided + why), writing only the `resolution` block so the provenance hash over the immutable decision set survives. `lzctl gap add` registers an agent-discovered gap as an OPEN item and refuses to re-stamp an already-edited set.
- **`lzctl status --json`**: the phase report as a machine contract, every phase derived from artifacts on disk rather than a stored pointer — edit the spec and the tree reports `recheck` on its own. `lzctl back <phase>` records a journaled re-entry (who, why, what it invalidates) and deletes nothing. Exit 0 on track / 2 recheck / 3 blocked.
- **Rendering design system** for agent replies (`skills/huawei-cloud-landing-zone/SKILL.md` + `rendering.md`): verdict first, exceptions only, one Next block with its runner/cloud/undo provenance, words only. Phases render zero-padded (`03-build`). The CLI emits data; the agent renders it.
- **LZR-032** fails validation on unresolved `REPLACE_WITH_` placeholders (VPN PSK exempt by design); **LZR-033** blocks `enable_hss` / `enable_dbss`, now documented as RESERVED.

### Changed

- **`export_handover.py` folded into `export_v2.py`**. It existed only to be imported and have its exclusion globals reassigned at runtime; the exporter is now self-contained and the doctrine guard that anticipated the fold targets it directly. The secmaster feature strip was a six-operation mini-DSL driving one registry entry against one env — now straight-line code. Handover output verified byte-identical across 131 files.
- **`deps.json` has one owner**: `lzctl deps` (and `lzctl build`). `depsgraph.py` keeps its library API but no longer ships a second CLI; its topological sort is now `graphlib.TopologicalSorter`. LZR-008's remediation text names the current command.
- Removed flags nothing passed (`plan_triage --rules`, `export_v2 --no-docs`, `depsgraph --quiet`, the eval `--adapter`) and one-caller wrappers, duplicated emitter write loops, and an always-empty error-scoping layer. Generated env tree verified byte-identical across 144 files.

### Removed

- Derived artifacts no longer committed: eval `scores.json` / `scores-rescored.json` (nothing reads them back; `run_eval.py --rescore <dir>` regenerates them from the committed transcripts), superseded scratch runs, and archived copies of the bench scripts that had drifted from their `e2e_bench/` originals. `tests/evaluation/results/` and `releases/` are now gitignored; the runs of record predate the rule and remain.
- `fixtures/make_example.py` — a 368-line generator kept beside its committed output with zero callers, synchronized by hand.

- **Breaking (state layout)**: four env state keys carried a stale numbering (`07-security` wrote to `envs/10-security/`, `08-network-dns` to `envs/07-dns/`, `09-network-cfw` to `envs/08-cfw/`, `11-network-sgacl` to `envs/09-network-sgacl/`). Keys now match the env directory names, guarded by a regression test. Deployments created from 0.1.0 need a one-time `terraform init -migrate-state` per affected env.

## 0.1.0 — 2026-08-31

Initial public release.

### Capabilities

- **Spec pipeline**: JSON spec as the authoritative store (the Excel workbook is a generated artifact); `intake` → `assess` → `validate` → `build` with byte-identical regeneration enforced by the harness.
- **Runner (`lzctl`)**: ordered plan/apply from `deps.json`, plan triage (exit 0 clean / 2 changes / 3 destructive), state backup before every apply, drift sweeps, post-apply `verify` gate, `report` evidence bundles, `adopt` import helper, `preflight` environment checks.
- **Terraform library**: 15 plain-HCL modules + 12-env scaffold covering the 9 CAF governance domains, with a vendored-snapshot sync story (`tools/sync_modules.py`, `PROVENANCE.md`).
- **Agent skill** (`skills/huawei-cloud-landing-zone/`): phase-routed domain design rules over 27 topic assets; companion `questionnaire-to-spec` skill.
- **Delivery**: profile-driven artifact export (`export_v2`) with feature strips, release metadata, and the standalone runner shipped inside; generated customer doc set (`lzctl docs`).
- **Assessment chain**: schema-derived questionnaire with build-failing coverage check; mechanical dump; deterministic three-bucket assessment that never guesses.
- **Verification**: 7-check regression harness (`python -m lz_spec.verify_pipeline`) + pytest bridge; generated JSON Schema for model-agnostic spec validation.

### Safety additions in this assembly

- **Retry-once** on documented transient platform signatures only (`LZ_TRANSIENT_SIGNATURES`, default `LTS.2101,EPS.0004`) — re-plan + apply, never a stale-plan replay.
- **Destructive double-confirm**: exit-3 plans block apply; proceeding needs `--allow-destroy` plus a typed env-name confirmation that `--yes` never bypasses (`--destroy-confirm <env>` for CI).
- **Fail-loud region**: `Global.Settings.home_region` is required with no default — a missing region fails the build instead of deploying somewhere plausible.
- **Leak guard**: export tests derive forbidden customer tokens (including on-prem CIDR prefixes, domains, and email domains) from every non-example profile and scan example specs and exported artifacts.

### Hardening and tooling added during review

- E2E engineer-roleplay model benchmark (`tests/evaluation/e2e_bench/`, `--smoke` for a free setup check); run of record committed under `tests/evaluation/results/e2e-roleplay-20260831/`.
- Skill install routes: `npx skills` one-liner, Claude Code plugin marketplace (`.claude-plugin/`), manual copy.
- Plain-terms sweep of user-facing text: customer ID (was slug), `--spec` on build/docs (`--ir` kept as alias), platform rules, design rules, authoritative store.
- Documented where Claude coupling lives vs the model-independence claim (README + bench scope note).
- Cleanup: unreferenced cicd-plan.md removed; legacy import shim bypassed.
- Security-review hardening (two external rounds): app UI CSRF token + origin check + workspace-confined save paths; export refuses to clear non-export targets and fails closed on strip misses; apply blocked on placeholder VPN PSKs; secrets never .bak'd; atomic/owner-checked apply lock with per-env refresh; saved-plan staleness covers the modules tree; CI terraform validation made real; CFW rejects multiple domain groups per rule; sync_modules overlap guard.
