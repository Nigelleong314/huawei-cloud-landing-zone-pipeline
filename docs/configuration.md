# Configuration

## Environment variables

| Variable | Used by | Meaning | Default |
|---|---|---|---|
| `LZ_MODULE_SOURCE_ROOT` | build (emitters) | Where emitted env HCL finds the module library, **relative to each env dir** | `../../modules` (matches the product layout: `<workspace>/modules` beside `<workspace>/envs/NN-*`) |
| `LZ_TRANSIENT_SIGNATURES` | `lzctl apply` | Comma-separated substrings of platform errors that merit exactly one retry (re-plan + apply). Keep signatures specific | `LTS.2101,EPS.0004` |
| `LZ_VERIFY_IR` | `lz_spec.verify_pipeline` | Spec the regression harness runs against | `pipeline/lz_pipeline/fixtures/example.spec.json` |
| `LZ_VERIFY_ENVS` | `lz_spec.verify_pipeline` | Envs tree the harness runs against | `terraform/envs-example` |
| `LZ_PRICING_REGION` | plan triage cost report | Selects `tools/pricing/<region>.json` as the rate card | explicit `--pricing` path, else the single card in `pricing/` if only one exists |
| `LZ_WORKSPACE` | `lz-app` | Workspace root for the spec editor (alternative to `--workspace`) | walk-up from CWD |
| `LZ_SPEC_DIR` | `python -m lz_pipeline` | Override the `lz_spec` location | next to the package |
| `HW_ACCESS_KEY` / `HW_SECRET_KEY` | build | Huawei AK/SK written into each env's gitignored `secrets.auto.tfvars.json`. Unset → the file is skipped with a note. **Never in the spec** — the schema says so explicitly | unset |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | terraform (OBS S3 backend) | Backend credentials (the OBS S3-compatible endpoint speaks AWS auth) | unset — `preflight` fails |
| `AWS_REQUEST_CHECKSUM_CALCULATION` | terraform ≥ 1.11 + OBS backend | Must be `when_required` or state save fails **after** apply | checked by `preflight` |
| `AWS_RESPONSE_CHECKSUM_VALIDATION` | terraform ≥ 1.11 + OBS backend | Must be `when_required` (same failure mode) | checked by `preflight` |

## Customer workspace layout

A customer engagement lives in a DATA directory outside this repo:

```text
<workspace>/
  specs/                       lz.spec.<customer>.json + lz.spec.<customer>.decisions.md
  envs/                        00-bootstrap ... 11-network-sgacl
    deps.json                  generated apply order (do not hand-edit)
    .lzctl.lock                transient advisory lock
    lzctl-logs/                timestamped run logs
    state-backups/             pre-apply state pulls
    evidence/<ts>/             lzctl report bundles
  modules/                     copy of terraform/modules (snapshot for this customer)
```

`lzctl assess --workspace <dir>` creates `specs/`; `lzctl build --scaffold-dir` populates `envs/`. The `envs/` ↔ `modules/` siblinghood is what the default `LZ_MODULE_SOURCE_ROOT=../../modules` assumes; override it for any other shape. The in-repo example (`terraform/envs-example` beside `terraform/modules`) has the same relationship.

Per env, generated files (never hand-edit): `terraform.tfvars.json`, `backend.hcl`, `*.generated.tf`, `secrets.auto.tfvars.json` (gitignored). Static files come from `terraform/scaffold/`.

## Profiles

Export profiles (`pipeline/lz_pipeline/profiles/*.json`) drive `python -m lz_pipeline.export_v2`; paths resolve against the invoking workspace:

```json
{
  "customer": "example",
  "features": {"secmaster": true},
  "envs_dir": "terraform/envs-example",
  "docs_dir": null,
  "ir": "pipeline/lz_pipeline/fixtures/example.spec.json"
}
```

A feature disabled in the profile is stripped from the staged artifact at generation time — exports are always re-runnable; artifact surgery is never needed.

## Rate cards

`pipeline/lz_pipeline/tools/pricing/<region>.json`:

```json
{
  "region": "ap-southeast-3",
  "currency": "USD",
  "hours_per_month": 720,
  "rates": { "cfw.instance": null }
}
```

`null` rates render as RATE NOT SET (quantities are still reported). Resolution order: `--pricing` path → `pricing/<LZ_PRICING_REGION>.json` → the single card in `pricing/` if exactly one exists → empty card. **The cost report always names the card's region**, so a mismatched card is visible instead of silently plausible.

## The spec schema

- `pipeline/lz_spec/schema.py` — the authoritative schema (every sheet, table, column, type, sample, description).
- `schemas/lz.spec.schema.json` — a generated JSON Schema so any validator (or agent harness) can check a spec without importing the pipeline. Regenerate after any schema change:

```bash
python -m lz_pipeline.tools.gen_jsonschema -o schemas/lz.spec.schema.json
```

Notable schema facts:

- `format` must match `lz-spec-ir/`; `schema_version`, `customer`, and `sheets` are required.
- `Global.Settings.home_region` is **required with no default** — a missing region fails the build loudly.
- AK/SK never live in a spec; the `Global` sheet description says to pass them via `HW_ACCESS_KEY` / `HW_SECRET_KEY`.
