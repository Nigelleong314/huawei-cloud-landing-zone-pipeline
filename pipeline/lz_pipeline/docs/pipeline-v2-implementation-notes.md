# Pipeline v2 — Implementation record (Phases 0–5)

**Date:** 2026-07-13 · implements `pipeline-v2-architecture-proposal.md`
**Frozen reference:** `backups/pipeline-archive-2026-07-12/` (the pre-v2 pipeline; every phase A/B-tested against it)

## Verification model (ran at every phase exit)

| Gate | Proves |
|---|---|
| `verify_pipeline.py regen-diff` | live envs-acme regeneration is a byte no-op |
| `lz_pipeline/tools/ab_check.py` vs the frozen archive | old pipeline and new pipeline produce identical bytes from the same workbook (37 files, 0 diffs) |
| `lz_pipeline/tests/test_goldens.py` | 72 golden files (acme + acme fixtures) reproduced byte-for-byte |
| `verify_pipeline.py validate` | `terraform validate` green in all 11 live envs |
| unit suites (`lz_pipeline/tests/test_phase*.py`, ~90 checks) | every new subsystem, incl. failure paths |
| acme fixture (`lz_pipeline/fixtures/`) | nothing is hardcoded to the customer: different region (ap-southeast-1), supernet (10.42.0.0/16), naming style, CFW/NAT off, WAF **on**, one detached spoke — builds all 11 envs, `terraform validate` green, zero the customer strings in output |

Final state: **all gates green** (regen-diff, validate, template-check, rules, deps, unit, goldens, A/B; opa reported SKIPPED — no conftest/opa binary on this machine, wiring in place).

## Phase 0 — guardrails

- `_meta` sheet + `SCHEMA_VERSION` in `schema.py`/template; parser defaults missing `_meta` to 1.0 (the customer untouched).
- `lz_pipeline/rules.py`: LZR rule registry — 19 executable checks (CIDR format/containment/overlap, DNS resolver-VPC membership, CFW group overlap/enums/refs/inbound-domain-group, StringLike wildcards, PSK-in-sheet, email format, backend skip-flags, SCP-v5 scan, perimeter-enforce warning) + 16 registry entries documenting where runtime rules are enforced. Wired into `build_envs` (errors block builds) and `verify`. the customer: 0 findings.
- `lz_pipeline/depsgraph.py`: env DAG derived from `terraform_remote_state` usage (keys resolved through variables.tf defaults + tfvars); emits `deps.json`; asserts producer-before-consumer (LZR-008). the customer DAG: 02–06←01; 07/08/09←01+05; 10←01+05+06.
- `lz_pipeline/tools/plan_triage.py`: plan-JSON classifier (benign LZR-019 registry, destructive detection, protected types incl. `vpn_gateway`); exit codes 0/2/3.
- `lz_pipeline/tools/{gen_ipam,gen_checklist,gen_config_book}.py` (+`envtree.py`): the scratchpad docgen scripts promoted and genericized — alias→account mapping **parsed from provider files** rather than hardcoded. Reproduce the customer deliverables exactly (checklist: 217 rows / 597 instances).
- `lz_pipeline/tools/ab_check.py`: the old-vs-new A/B harness. OPA graceful wiring in verify.

## Phase 1 — spec IR

- `lz_pipeline/` package: `model.py` (IR = versioned JSON of the parsed workbook; exact round-trip proven), `schema_check.py` (dependency-free structural validation from `schema.SHEETS`; coercion-aware types), CLI verbs `spec-export` / `spec-validate` / `build --ir`.
- `lz_spec/lz.spec.acme.json` committed — the diffable system-of-record snapshot.
- Gate: IR-path build == workbook-path build, **36 files byte-identical**. schema_check surfaced two real drift warnings (workbook `cts_tracker_region` field and withdrawn `GatewayRoutes` table unknown to schema.py).

## Phase 2 — engine split

- `build_envs.py` (2,639 lines) mechanically split (AST-based, bodies verbatim) into `lz_pipeline/core/`: `parsing`, `validation`, `builders`, `writer`, `helpers`, `cli`, and `emitters/{common,finance,identity,perimeter,observability,network}`. `build_envs.py` is now a compatibility shim (same CLI, same import surface).
- HCL extraction pattern established: `core/templating.py` (dependency-free `${}` renderer) + `core/templates/*.tf.tmpl` — the three shared provider blocks and the finance/identity module calls now render from template files. Remaining emitters keep composed lines inside their small modules; converting them is mechanical under the golden gate. *(Deliberate partial — documented deviation.)*
- `core/ownership.py`: cross-env shared-resource registry (dns query-log 06→07, flow-log groups 05→06, CFW streams 05→06, SMN topics 06→10) — captures the data-source ordering dependencies the remote-state DAG can't see; enforced in verify.
- Gates: goldens byte-identical for both fixtures; regen-diff and A/B green through the shim.

## Phase 3 — derivation + template v2

- Flow-log converge rows are derived automatically on every build (`core/cli.derive_flowlog_converge`): an EMPTY 06_Observability.LogConverge table is filled with one `<vpc>-flowlog` row per VPC (hub + spokes); a curated table is authoritative and left untouched. The former `resolver/` package (CIDR/subnet/attachment derivation, naming grammar, IPAM allocator, profiles) and the `resolve` CLI verb were REMOVED 2026-07-26 — every spec value is now explicit.
- Schema v2: `SCHEMA_VERSION = 2.0`. CLI verb `migrate` (v1->v2). The resolver-era `ERAttach` + `SubnetProfile` columns were dropped from `SpokeVPCs` with the resolver (builders never read them; attachment intent lives in SpokeERAttachments — no row = isolated spoke).
- Template v2 (`gen_template.py`): **67 dropdowns** (all bool columns, 19 enum columns, 14 FK pick-lists referencing the ranges where target names are typed) + derived-column grey striping and annotations.
- Gates: `tests/test_converge.py` — flow-log converge derivation (empty table fills, curated untouched, both toggles gate it) + the customer builds byte-identical to the goldens.

## Phase 4 — lzctl runner

- `lz_pipeline/lzctl.py`: standalone (stdlib-only) runner — `preflight` (terraform version, the four env vars incl. the checksum values, deps.json), `order`/`plan`/`apply` (DAG-ordered; advisory lock with stale-breaking; `state pull` backup before every apply; plan saved to file; **triage gate stops on destructive changes** unless `--allow-destroy`; logs under `lzctl-logs/`), `drift --report`, `state-backup`, `adopt` (import + plan-until-clean), `who-changed`, `triage`, `docs` (runs the three generators), plus delegates to pipeline verbs that degrade gracefully in a runtime-only install.
- Gates (19 checks, zero credentialed operations): deps-ordered sequencing, preflight diagnostics incl. wrong checksum value, lock lifecycle, dry-run command trace over the live tree, triage exit codes, standalone operation from a directory without lz_spec.

## Phase 5 — export/release v2

- `lz_pipeline/export_v2.py` + `profiles/{acme,acme}.json`: profile-driven export reusing the legacy copier. Feature flags strip at **generation** time via a data-driven op registry (`FEATURES`); ships `runner/` (lzctl + plan_triage), `envs/deps.json`, `VERSION`, `CHANGELOG.md` derived from the spec-IR diff against release snapshots (`lz_spec/releases/<customer>/<ver>/`), and a MANIFEST carrying customer/version/schema/features coordinates. `--compat` reproduces the legacy artifact for the oracle test.
- **Oracle result** (vs the live shipped artifact, 247 files): file sets match; the SecMaster strip is **byte-identical to the reviewed hand-edit** (0 diffs in 10-security); the only content diffs are 10 files where the **live artifact is stale** (in-place edits re-copied source scaffold files without the `.generated.tf` comment rename — the export's text is the correct one). Frozen-export problem solved: `features.secmaster=false` is now one profile line.
- acme export: all release files present, secmaster kept (feature on), **zero the customer strings** anywhere under `envs/` (three scaffold sample-text leaks found and genericized in `envs-v2` — live envs-acme copies untouched).
- Changelog gate: second release lists the spec delta ("added ACME-Prod-B").

## Deviations from the proposal (documented)

1. **Emitter templating is partial** (Phase 2): pattern + renderer + goldens exist; provider blocks and two emitters converted; observability/network/perimeter emitters still compose lines in Python (in small modules). Continuing is mechanical and golden-gated.
2. **OPA remains SKIP** on this machine (no conftest/opa binary); the verify hook is in place.
3. **Nothing is derived except flow-log converge rows** (2026-07-26): CIDR/subnet/attachment derivation and the naming grammar were removed with the resolver — every spec value is explicit, which is what the live customer always was.
4. **lzctl lock is machine-local advisory** (per proposal T6); CI concurrency groups remain the cross-machine serializer.
5. Live-artifact staleness (10 files) reported, not "fixed" in place — the next real export supersedes them.

## Re-running everything

```
cd lz_spec
py verify_pipeline.py                      # regen-diff, validate, template-check, rules, deps, unit(≈90 checks), opa
py ..\lz_pipeline\tools\ab_check.py --old "..\backups\pipeline-archive-2026-07-12\lz_spec" --new . --workbook "landing_zone_spec - acme.xlsx"
cd ..\lz_pipeline
py tests\test_goldens.py                   # 72 golden files, both fixtures
py fixtures\make_acme.py     # regenerate fixtures
```
