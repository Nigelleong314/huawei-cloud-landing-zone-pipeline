# Development

## Running from a plain checkout

`pip install -e .` is the normal development mode. Checkout execution without
installing is supported for CI/debugging: the root `conftest.py` puts
`pipeline/` and `app/` on the path (for pytest **and** the subprocesses it
spawns); outside pytest, set it yourself:

```bash
# Linux/macOS                               # Windows
export PYTHONPATH=$PWD/pipeline:$PWD/app    set PYTHONPATH=%CD%\pipeline;%CD%\app
python -m lz_pipeline.lzctl --help
```

## Running the tests

```bash
pytest                              # unit tier (default; eval + integration deselected)
pytest -m integration               # wheel-install contract (needs pip + venv, ~1 min)
python -m lz_spec.verify_pipeline   # full regression harness (7 checks) — also `lzctl check`
```

Details, including the leak guard and the golden-file workflow: `docs/testing.md`.

## Adding another model

The executed eval harness lives in `tests/evaluation/`: `adapter.py` exposes
one `run_model()` behind named adapters (the first shells out to headless
Claude Code — `claude -p --output-format json`; other providers plug in by
adding a function to `ADAPTERS`), `fixtures/fixtures.json` holds
self-contained single-turn tasks, and `run_eval.py` runs the model matrix
with deterministic scoring only, a cost ledger, and committed transcripts
under `results/` (fixture-declared secrets are redacted before anything is
persisted). Run it with `python tests/evaluation/run_eval.py --models <ids>
--trials N`. Because every model-facing surface is a file or CLI, adding a
model means adding an adapter, not touching the pipeline. Current results are
an **initial model-compatibility evaluation** (see `docs/testing.md`), not a
completed model-agnostic validation.

## Extending the skill

The skill is a routing table over topic assets. To add a topic: create
`skills/huawei-cloud-landing-zone/assets/<topic>/README.md`, then add one
routing row to the table in `skills/huawei-cloud-landing-zone/SKILL.md`.
Keep doctrine in the asset; keep the SKILL.md row to one line.

## Where changes land

- **Schema change** (`pipeline/lz_spec/schema.py`) → wire through
  `core/builders.py`, regenerate the template and the questionnaire, recapture
  goldens, `lzctl check`.
- **New/changed module** (`terraform/modules/`) → update `terraform/scaffold/`
  if env composition changes, rebuild `terraform/envs-example`, recapture
  goldens.
- **Workflow change** (phases, gates) → `schemas/phases.json` first, then
  `docs/workflow.md` and the skill's Phase contract table (they render it).
