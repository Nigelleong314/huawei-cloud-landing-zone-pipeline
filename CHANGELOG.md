# Changelog

## Unreleased

- E2E engineer-roleplay model benchmark (`tests/evaluation/e2e_bench/`, `--smoke` for a free setup check); run of record committed under `tests/evaluation/results/e2e-roleplay-20260831/`.
- Skill install routes: `npx skills` one-liner, Claude Code plugin marketplace (`.claude-plugin/`), manual copy.
- Plain-terms sweep of user-facing text: customer ID (was slug), `--spec` on build/docs (`--ir` kept as alias), platform rules, design rules, authoritative store.
- Documented where Claude coupling lives vs the model-independence claim (README + bench scope note).
- Cleanup: unreferenced cicd-plan.md removed; legacy import shim bypassed.

## 0.1.0 — 2026-08-30

Initial public-ready assembly.

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
