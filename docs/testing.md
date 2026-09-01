# Testing

## Running everything

```bash
pytest                              # unit suites via the pytest bridge
python -m lz_spec.verify_pipeline   # the full regression harness (7 checks)
```

`tests/unit/test_suites.py` is a thin pytest bridge over the self-contained assert-script suites (each exits non-zero on failure); it gives them discovery and per-suite reporting without rewriting them. Eval tests are marked `eval` and integration tests (pip/venv or terraform) are marked `integration`; both are excluded by default (`addopts = "-m 'not eval and not integration'"` in `pyproject.toml`). The default unit tier needs Python + openpyxl only — no Terraform (CI runs it without one; `test_phase4` degrades its binary-dependent check gracefully).

## The suites

Seven pipeline suites (`pipeline/lz_pipeline/tests/`) plus the app suite (`app/tests/test_app.py`):

| Suite | Proves |
|---|---|
| `test_phase0.py` | Platform rules (the LZR-### registry) |
| `test_phase1.py` | Workbook round-trip (spec ↔ generated workbook) |
| `test_converge.py` | Log auto-derivation |
| `test_cost.py` | Cost estimation |
| `test_goldens.py` | Artifact consistency against locked golden outputs |
| `test_phase4.py` | Runner workflow (`lzctl`) |
| `test_phase5.py` | Artifact export — including the leak guard |
| `app/tests/test_app.py` | The spec-editor app |

## The verify harness: 7 checks

`python -m lz_spec.verify_pipeline [check]` — run all checks, or a single check `regen-diff`, `validate`, `template-check`, `rules`, `deps`, `fmt`, `unit`. Targets default to the example spec + `terraform/envs-example`; point it at a customer workspace with `LZ_VERIFY_IR` and `LZ_VERIFY_ENVS`. Exit 0 = all requested checks passed.

| Check | What it proves |
|---|---|
| `regen-diff` | Rebuilding the envs from the spec is a **no-op**: every generated file (`terraform.tfvars.json`, `*.generated.tf`) is byte-identical, none missing, none new. This is the determinism guarantee. Secrets are stripped from the environment before the rebuild so verify never (re)writes them. |
| `validate` | `terraform validate` passes in every initialized env (skipped when terraform is absent or no environment is initialized). |
| `template-check` | The blank workbook template's sheets/tables/columns match a fresh generation from `schema.py` — i.e. the shipped template is not stale. |
| `rules` | The LZR platform-rule registry: spec rules on the spec + tree rules on the envs, zero error-severity findings. |
| `deps` | `deps.json` matches a fresh dependency graph from `terraform_remote_state` references (ordering, ownership registry, freshness). |
| `fmt` | `terraform fmt -check` on hand-written HCL (`terraform/modules`, `terraform/scaffold`). Generated files are governed by goldens instead. |
| `unit` | All suites in the table above, run as scripts. |

## The leak guard

Lives in `test_phase5.py` (artifact export). Customer identifiers are **derived, not listed**: for every non-example export profile, the guard loads that profile's spec and harvests forbidden tokens automatically — so onboarding a customer extends the check with no regex to remember. Harvested per spec:

- the customer ID; account, OU, cost-center, and hub/spoke VPC names;
- the spoke private supernet's leading octets;
- **on-prem classes** — identifiers that leak through the firewall/DNS payload, not just account names: CFW address-group names and member CIDR prefixes (first three octets, skipping the well-known private roots `10.0.0.` / `172.16.0.` / `192.168.0.` and whole RFC1918 blocks), CFW domain-group members, DNS resolver-rule domains, and account-email domains.

Tokens are lowercased and length-filtered (≥ 5 chars), then scanned against:

1. **the example specs** (`fixtures/example.spec.json` and every `pipeline/lz_spec/lz.spec.*.json`) — zero customer-derived strings allowed. This is the control that failed when an example spec once shipped with live on-prem data;
2. **the exported artifact** — every `.tf`/`.json`/`.hcl`/`.md`/`.example` under `envs/`, plus the generated workbook (schema descriptions and sample rows ship there too).

The export test also asserts no `secrets.auto.tfvars.json` ships in any artifact.

## The eval suite

`tests/evaluation/` holds the executed model-evaluation harness:

- `adapter.py` — model adapters behind one `run_model()` call. The first
  implementation shells out to headless Claude Code (`claude -p
  --output-format json`) from an empty temp cwd for context isolation; other
  providers plug in by adding a function to `ADAPTERS`.
- `fixtures/fixtures.json` — self-contained single-turn tasks across ten
  categories (requirement extraction, missing-information detection,
  normalization, invalid-input rejection, tool selection, tool arguments,
  workflow sequencing, destructive-apply safety, failure recovery,
  ambiguity escalation). Every fixture embeds its own design rules, so all
  models receive identical context.
- `run_eval.py` — matrix runner with **deterministic scoring only** (json
  shape/equality, regex presence/absence, exact match — never a judge
  model), a per-run cost ledger from the CLI's `total_cost_usd`, committed
  transcripts under `results/<ts>/`, and `--rescore <dir>` to re-score saved
  transcripts after scorer changes without new model calls.

Run it: `python tests/evaluation/run_eval.py [--models a,b,c] [--trials N]`.

Executed results live in `tests/evaluation/results/`. Read them as an
**initial model-compatibility evaluation**, not a completed model-agnostic
validation: the first matrix was 60 runs (3 capability tiers x 10 fixtures
x 2 trials). Of its 4 original failures, 3 were scorer proxy defects and 1
was a format slip recovered by tolerant extraction; after the scorer fix all
4 cells were re-executed live and passed. The transcripts are the committed
evidence; the score files are derived from them and regenerated on demand with
`--rescore <dir>`. A larger matrix (more fixtures, ~10 trials,
variance reporting) is the documented next step. Read the committed
results with the n in mind: cells are 2 trials each, so a 1/2 or 0/2 is
indistinguishable from noise - conclusions need the larger matrix. One
known scorer bias: deterministic `must_contain` patterns reward phrasing,
which subtly favors models whose style matches the fixture author's;
the tradeoff is accepted because it avoids model-graded evaluation.

`tests/evaluation/e2e_bench/` is the second, heavier instrument: a full
engineer-roleplay benchmark (fresh sandbox, minimal prompts, deterministic
workspace scoring — the model's own report is never trusted). One command
per model matrix; see its README. Run of record:
`tests/evaluation/results/e2e-roleplay-20260831/`.

One open model-behavior finding, kept as a strict regression canary
(`secrets-01`): asked to handle a secret a customer pasted into a
questionnaire answer, every tier correctly keeps it out of the spec, but
some models quote the pasted value back in their explanation even when
the design rules explicitly forbid re-emission - in one case inside the very
sentence promising not to. The deterministic layer keeps the SPEC clean
regardless; the canary tracks whether models stop echoing secrets into
transcripts and logs.
Tolerant JSON extraction in the scorer mirrors production consumption: a
model that wraps correct JSON in prose fails the *format* instruction but
not the schema check — the deterministic layer compensating for model
weakness is exactly the architecture under test.
