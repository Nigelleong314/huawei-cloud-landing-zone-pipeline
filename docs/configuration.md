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
| `HW_ACCESS_KEY` / `HW_SECRET_KEY` | terraform (provider) | Huawei AK/SK. Read straight from the environment — never written to disk. **Never in the spec** — the schema says so explicitly | unset — provider fails |
| `HW_SECURITY_TOKEN` | terraform (provider) | Session token, required **only** for a temporary AK/SK; must pair with the key it was minted from | unset |
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

Per env, generated files (never hand-edit): `terraform.tfvars.json`, `*.generated.tf`. Static files come from `terraform/scaffold/`; the build fills the state bucket and region into the inline `backend "s3"` block of each `providers.tf`, so `terraform init` takes no flags. Credentials are never among them — they live only in the environment (`HW_ACCESS_KEY` / `HW_SECRET_KEY` / `HW_SECURITY_TOKEN`, mapped to `AWS_*` for the backend).

## Profiles

Export profiles (`pipeline/lz_pipeline/profiles/*.json`) drive `python -m lz_pipeline.export_v2`. Relative paths resolve against the **profile file's directory**, so an export runs the same from any working directory (a path that only exists relative to the current directory still resolves there, with a note):

```json
{
  "customer": "example",
  "features": {"secmaster": true},
  "envs_dir": "../../../terraform/envs-example",
  "docs_dir": null,
  "ir": "../fixtures/example.spec.json"
}
```

Optional curation keys:

- `skip_envs` — env directories that are not shipped (e.g. a hand-managed env); they are also dropped from the shipped `deps.json`, with a warning when a shipped env consumes one.
- `ship_markdown` — `false` drops every `.md` under the artifact's `modules/` and `envs/` (default `true`).

Library modules no shipped env references are pruned automatically, and an env module source that does not resolve inside the artifact's `modules/` refuses the export. Env module sources are rewritten from `LZ_MODULE_SOURCE_ROOT` (the root the tree was built against — set it for the export too) to the artifact's `../../modules/`. No `*.tfstate*` file ever ships — including the `00-bootstrap` local state, which is handed over out of band.

A feature disabled in the profile is stripped from the staged artifact at generation time — exports are always re-runnable; artifact surgery is never needed.

Set the same switch in the spec so the built tree already matches the artifact: `07_Security.Settings.enable_secmaster = FALSE` makes `build` strip SecMaster from `07-security` (the env keeps its directory and number; edge protection stays), and the export strip is then a no-op. Turning it back on needs a rebuild with `--scaffold-dir` to restore the scaffold files.

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

## Comments in generated Terraform

The artifact is read by someone with no access to the workbook, the generator,
the issue history or us. Comments say what the configuration does and what
will bite the reader - nothing else.

    # --- Section title ---      every .tf opens with one; also marks groups
    # Note: One sentence.        a fact or instruction, sentence case, full stop
    # Short label                terse phrase directly above what it describes
    # Values: a, b               accepted values of the attribute below
    # Account: NAME              per-block label in a generated fan-out

Never ship change history ("removed", "no longer", "previously"), roadmap
notes (TODO, "deferred until", "parked"), provenance ("GENERATED by
build_envs", workbook sheet names), references to documents that do not ship,
or dates. If such a note carried a real fact, keep the fact and drop its
history.

`py -m lz_pipeline.comment_lint <dir>` checks a tree and exits non-zero with
file:line. **`export_v2` runs it over the assembled artifact and refuses to
build one that fails**, so a non-compliant tree cannot reach a customer.
