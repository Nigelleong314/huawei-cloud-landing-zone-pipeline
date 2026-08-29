# Testing

## Running everything

```bash
pytest                              # unit suites via the pytest bridge
python -m lz_spec.verify_pipeline   # the full regression harness (7 checks)
```

`tests/unit/test_suites.py` is a thin pytest bridge over the self-contained assert-script suites (each exits non-zero on failure); it gives them discovery and per-suite reporting without rewriting them. Eval tests are marked `eval` and excluded by default (`addopts = "-m 'not eval'"` in `pyproject.toml`).

## The suites

Seven pipeline suites (`pipeline/lz_pipeline/tests/`) plus the app suite (`app/tests/test_app.py`):

| Suite | Proves |
|---|---|
| `test_phase0.py` | Platform rules (the LZR registry) |
| `test_phase1.py` | Workbook round-trip (spec ↔ generated workbook) |
| `test_converge.py` | Log auto-derivation |
| `test_cost.py` | Cost estimation |
| `test_goldens.py` | Artifact consistency against locked golden outputs |
| `test_phase4.py` | Runner workflow (`lzctl`) |
| `test_phase5.py` | Artifact export — including the leak guard |
| `app/tests/test_app.py` | The spec-editor app |

## The verify harness: 7 checks

`python -m lz_spec.verify_pipeline [check]` — run all, or one of `regen-diff`, `validate`, `template-check`, `rules`, `deps`, `fmt`, `unit`. Targets default to the example spec + `terraform/envs-example`; point it at a customer workspace with `LZ_VERIFY_IR` and `LZ_VERIFY_ENVS`. Exit 0 = all requested checks passed.

| Check | What it proves |
|---|---|
| `regen-diff` | Rebuilding the envs from the spec IR is a **no-op**: every generated file (`terraform.tfvars.json`, `*.generated.tf`) is byte-identical, none missing, none new. This is the determinism guarantee. Secrets are stripped from the environment before the rebuild so verify never (re)writes them. |
| `validate` | `terraform validate` passes in every initialized env (skipped when terraform is absent or no env is init'ed). |
| `template-check` | The blank workbook template's sheets/tables/columns match a fresh generation from `schema.py` — i.e. the shipped template is not stale. |
| `rules` | The LZR platform-rule registry: spec rules on the IR + tree rules on the envs, zero error-severity findings. |
| `deps` | `deps.json` matches a fresh dependency graph from `terraform_remote_state` references (ordering, ownership registry, freshness). |
| `fmt` | `terraform fmt -check` on hand-written HCL (`terraform/modules`, `terraform/scaffold`). Generated files are governed by goldens instead. |
| `unit` | All suites in the table above, run as scripts. |

## The leak guard

Lives in `test_phase5.py` (artifact export). Customer identifiers are **derived, not listed**: for every non-example export profile, the guard loads that profile's spec IR and harvests forbidden tokens automatically — so onboarding a customer extends the check with no regex to remember. Harvested per spec:

- the customer slug; account, OU, cost-center, and hub/spoke VPC names;
- the spoke private supernet's leading octets;
- **on-prem classes** — identifiers that leak through the firewall/DNS payload, not just account names: CFW address-group names and member CIDR prefixes (first three octets, skipping the canonical private roots `10.0.0.` / `172.16.0.` / `192.168.0.` and whole RFC1918 blocks), CFW domain-group members, DNS resolver-rule domains, and account-email domains.

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
  ambiguity escalation). Every fixture embeds its own doctrine, so all
  models receive identical context.
- `run_eval.py` — matrix runner with **deterministic scoring only** (json
  shape/equality, regex presence/absence, exact match — never a judge
  model), a per-run cost ledger from the CLI's `total_cost_usd`, committed
  transcripts under `results/<ts>/`, and `--rescore <dir>` to re-score saved
  transcripts after scorer changes without new model calls.

Run it: `python tests/evaluation/run_eval.py [--models a,b,c] [--trials N]`.
Executed results (60-run matrix across three capability tiers) live in
`tests/evaluation/results/` with both the original and rescored score files.
Tolerant JSON extraction in the scorer mirrors production consumption: a
model that wraps correct JSON in prose fails the *format* instruction but
not the schema check — the deterministic layer compensating for model
weakness is exactly the architecture under test.
