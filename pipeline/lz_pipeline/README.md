# lz_pipeline — the landing-zone pipeline (v2)

All v2 pipeline code lives here. `../lz_spec/` keeps the customer DATA (the
committed JSON spec files and the generated blank template) plus the schema
layer and entry points (`schema.py`, `gen_template.py`, `verify_pipeline.py`,
`build_envs.py` — a shim over this package — and `export_handover.py`).

```
lz_pipeline\
├── core\               engine: parsing, validation, builders, writer, cli,
│   ├── emitters\       per-env HCL fan-out generators
│   ├── templates\      the HCL template files (*.tf.tmpl)
│   └── ownership.py    cross-env shared-resource registry
├── rules.py            LZR platform-rule registry (spec + tree checks)
├── depsgraph.py        env dependency graph -> deps.json (LZR-008)
├── lzctl.py            THE RUNNER (standalone; ships in customer artifacts)
├── export_v2.py        profile-driven artifact export + release metadata
├── profiles\           per-customer export profiles (acme.json, example.json)
├── tools\              plan_triage, gen_ipam, gen_checklist, gen_config_book, gen_workbook,
│                       gen_questionnaire + dump_questionnaire (pre-engagement assessment)
├── fixtures\           example synthetic customer
├── tests\              test_phase0..5, test_converge + goldens (72 locked output files)
├── releases\           per-customer release snapshots (created on export)
└── docs\               architecture proposal + implementation record
```

## Everyday commands (run from the workspace root `ldz\`)

Verify everything (also runs all unit suites):

    cd lz_spec && py verify_pipeline.py

Build (the json spec IR is the CANONICAL config store; the Excel workbook is
a generated artifact — `tools/gen_workbook.py` — not an input):

    py -m lz_pipeline build --ir lz_spec/lz.spec.acme.json --envs-dir huawei-lz/envs-acme

Ingest a workbook / validate a spec:

    py -m lz_pipeline spec-export lz_spec/landing_zone_spec.xlsx -o customer.spec.json
    py -m lz_pipeline spec-validate customer.spec.json
    py -m lz_pipeline build --ir customer.spec.json --envs-dir huawei-lz/envs-<name> --scaffold-dir huawei-lz/envs-v2

Pre-engagement assessment (upstream of the workbook; schema-coverage-checked):

    py lz_pipeline/tools/gen_questionnaire.py            # regen the blank questionnaire (workspace root)
    py lz_pipeline/tools/dump_questionnaire.py <filled.xlsx> -o dump.json   # then /questionnaire-to-spec

Operate a deployed tree:

    py lz_pipeline/lzctl.py preflight --envs-dir huawei-lz/envs-acme
    py lz_pipeline/lzctl.py plan  --envs-dir huawei-lz/envs-acme --all
    py lz_pipeline/lzctl.py apply --envs-dir huawei-lz/envs-acme <env>   # lock + backup + triage gate
    py lz_pipeline/lzctl.py drift --envs-dir huawei-lz/envs-acme --report drift.md
    py lz_pipeline/lzctl.py docs  --envs-dir huawei-lz/envs-acme --out-dir docs-out --customer "the customer Property"

Export a customer artifact (features come from the profile):

    py -m lz_pipeline.export_v2 --profile lz_pipeline/profiles/acme.json --target <dir> --version 1.1.0

Full details and per-phase evidence: `docs/pipeline-v2-implementation-notes.md`.
