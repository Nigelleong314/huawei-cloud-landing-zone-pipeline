# Repository shape and the codegen split [REUSABLE]

## Repository shape

```
modules/            one module per governance domain (main/variables/outputs/versions)
envs-<customer>/    numbered env dirs composing the modules
  00-bootstrap/     state bucket (LOCAL state, ships with the artifact)
  01-foundation/ …  every other env: OBS remote state
  deps.json         dependency graph -> apply order
spec (JSON)         canonical config; envs are GENERATED from it
```

- Module pattern: every variable typed + described, every output described.
  Tags come SOLELY from provider `default_tags` — modules never inject their
  own tag boilerplate.
- Env pattern: static scaffold files (`main.tf`, `providers.tf`,
  `variables.tf`, `backend.tf`, `versions.tf`, `outputs.tf`) + generated
  files (`terraform.tfvars.json`, `backend.hcl`, `*.generated.tf`,
  gitignored `secrets.auto.tfvars.json`).

## The codegen split (handover constraint — never violate)

The Terraform tree is handed to end users WITHOUT the spec pipeline. So:

- Put transformation and heavy lifting in the **generator scripts**, not HCL.
- Emitted envs must be plain, readable Terraform a human can edit; simple
  `for_each` over well-named objects is the complexity ceiling.
- `terraform plan/apply` must work from a checkout of envs + modules alone.
- Providers can't be `for_each`-ed: per-account fan-outs (provider alias +
  module call per account) are GENERATED files — one alias per account, one
  call per account; adding an account to the spec wires it everywhere.
- When adding a feature, ask: "could the end user adjust this behaviour by
  editing tfvars or a small obvious HCL block?" If not, move the complexity
  into the generator.

## Spec-driven generation pattern [ADAPTABLE]

- One JSON spec = the canonical store; schema (sheets → tables → typed
  columns) is the single source of truth for the editor UI, validators,
  Excel template, and generated workbook.
- Builders map sheet data → per-env tfvars; emitters write the per-account /
  per-VPC `*.generated.tf` fan-outs from shared HCL templates.
- Auto-derivation (e.g. a log-convergence table) fills empty tables at
  build time; a non-empty user table is authoritative and replaces the
  derivation entirely — never merge.
- Regeneration must be byte-identical when the spec hasn't changed
  (regen-diff gate); golden files lock expected output for every fixture.

## for_each key design

- Key resource maps on **stable input names**, never on another resource's
  attributes — attribute-keyed maps go known-after-apply and break
  plan/import.
- Content-address rule-like resources (e.g. security-group rules keyed
  `sg|dir|proto|ports|remote`) so editing one row never churns siblings.
- Keys that address live resources are contracts — see assets/state-surgery
  before renaming anything used as a `for_each` key.
