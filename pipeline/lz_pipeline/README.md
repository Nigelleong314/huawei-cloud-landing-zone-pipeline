# lz_pipeline — the landing-zone pipeline engine

All pipeline code lives here. `../lz_spec/` keeps the schema layer and entry
points (`schema.py`, `gen_template.py`, `verify_pipeline.py`, `build_envs.py`
— a shim over this package — and `export_handover.py`) plus the example spec.

```text
lz_pipeline\
├── core\               engine: parsing, validation, builders, writer, cli,
│   ├── emitters\       per-env HCL fan-out generators
│   ├── templates\      the HCL template files (*.tf.tmpl)
│   └── ownership.py    cross-env shared-resource registry
├── rules.py            LZR platform-rule registry (spec + tree checks)
├── depsgraph.py        env dependency graph -> deps.json (LZR-008)
├── lzctl.py            THE RUNNER (the `lzctl` console command)
├── export_v2.py        profile-driven artifact export + release metadata
├── profiles\           export profiles (example.json)
├── tools\              plan_triage, gen_ipam, gen_checklist, gen_config_book, gen_workbook,
│                       gen_questionnaire + dump_questionnaire (pre-engagement assessment)
├── fixtures\           example synthetic customer (example.spec.json)
├── tests\              test_phase0..5, test_converge + goldens (locked output files)
└── docs\               CI/CD plan
```

## Everyday commands (from the repo root; `pip install .` gives you `lzctl`)

Verify everything (also runs all unit suites): `lzctl check`

Build (the JSON spec is the AUTHORITATIVE config store; the Excel workbook is
a generated artifact — `tools/gen_workbook.py` — not an input):

    lzctl build --spec specs/lz.spec.acme.json --envs-dir envs --scaffold-dir terraform/scaffold

Ingest a workbook / validate a spec:

    python -m lz_pipeline spec-export landing_zone_spec.xlsx -o customer.spec.json
    lzctl validate customer.spec.json

Pre-engagement assessment (upstream of the workbook; schema-coverage-checked):

    python -m lz_pipeline.tools.gen_questionnaire       # regen the blank questionnaire
    lzctl intake <filled.xlsx> -o dump.json
    lzctl assess dump.json --customer <customer> --workspace .   # then skills/questionnaire-to-spec

Operate a deployed tree:

    lzctl preflight --envs-dir envs
    lzctl plan  --envs-dir envs --all
    lzctl apply --envs-dir envs <env>       # lock + backup + triage gate
    lzctl drift --envs-dir envs --report drift.md
    lzctl docs  --envs-dir envs --out-dir docs-out --customer "Acme Corp"

Export a customer artifact (features come from the profile):

    lzctl export --profile pipeline/lz_pipeline/profiles/example.json --target <dir> --version 1.0.0

The repo-level `README.md` and `docs/` carry the full workflow.
