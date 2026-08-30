# lz_spec — the schema layer and the spec store

The JSON spec files here are the **canonical configuration store** for the
landing zone. The Excel workbook is a generated artifact (an output for
customers), never an input.

## What's here

| File | Purpose |
|---|---|
| `schema.py` | Single source of truth: every sheet, table, column, type, sample, and description |
| `lz.spec.<slug>.json` | Customer- or environment-specific specification |
| `lz.spec.example.json` | Filled example spec — every fillable table populated |
| `gen_template.py` | Generates the blank `landing_zone_spec.xlsx` template from `schema.py` |
| `landing_zone_spec.xlsx` | The blank template (generated — regenerate after schema changes) |
| `verify_pipeline.py` | The regression harness: regen-diff, validate, template-check, rules, deps, fmt, unit suites |
| `build_envs.py` | Legacy workbook-path entry point (kept for the byte-identity test) |
| `export_handover.py` | Copy/rewrite helpers used by `lz_pipeline.export_v2` |

## Workflow

The normal way to edit a spec is the app:

    cd lz_app && py -m lz_app

It renders every sheet from `schema.py`, validates, builds, and runs the
pipeline jobs. The CLI equivalents:

    py -m lz_pipeline spec-validate lz_spec/lz.spec.acme.json
    py -m lz_pipeline build --ir lz_spec/lz.spec.acme.json --envs-dir huawei-lz/envs-acme
    cd lz_spec && py verify_pipeline.py          # the full gate; run after any change

Credentials never go in a spec file: each env's `secrets.auto.tfvars.json`
(gitignored) or the app's per-job credentials panel carries the AK/SK.

## Spec structure

A spec has one entry per sheet; each sheet holds tables of three kinds:

- **Scalar** (key/value) — settings; blank means "use the module default".
- **List** — one value per row (allowed regions, OU names).
- **Object table** — one row per item (account, VPC, firewall rule); optional
  tables have an `Enabled` column.

The sheet order is the apply order: `Global`, then `01_Foundation` through
`11_SGACL` map one-to-one onto the env directories (`01-foundation` …
`11-network-sgacl`), with `_meta` holding file info. The authoritative
sheet→env→module map is the Index sheet of the generated template.

## Adding a new field

1. Add the `KV(...)` row (or table column) in `schema.py`.
2. Wire it through the builder in `lz_pipeline/core/builders.py`.
3. Regenerate the template: `py gen_template.py landing_zone_spec.xlsx`.
4. Recapture goldens if generated output changes, then `py verify_pipeline.py`.
