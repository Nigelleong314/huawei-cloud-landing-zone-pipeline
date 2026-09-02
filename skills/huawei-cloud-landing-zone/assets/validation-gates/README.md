# Validation gates [IMPLEMENTATION]

Gates that keep a landing-zone estate correct, in the order they run.

## 1. Spec validation (before any build)

- **Structural**: every table/column matches the schema; types coerce;
  reserved tables must be empty.
- **Semantic**: cross-references resolve (every VPC, subnet, account, and
  enterprise-project name used is defined); CIDRs don't overlap; account
  names 6–32 chars with unique emails; OU depth ≤ 2.
- **Platform rules** (the "LZR" pattern — LZR = landing-zone rule, a
  registry of numbered rules, each either executable or documented-runtime):
  - Executable examples: SCP version must be 5.0; resolver rules must
    include the resolver VPC; private zones must list the resolver VPC;
    reserved-table rows fail validation; a VPN pre-shared key must not sit
    in the spec.
  - Documented-runtime examples: CTS region hard-coding, checksum env vars,
    assume-role mode selection, no-statics-to-VPN, EIP create-only
    replacement, provider version pins.
  Keep rules numbered (LZR-001…) so findings, docs, and CI gates share one
  vocabulary.

## 2. Regression harness (after every pipeline or module change)

Seven checks, all must pass:

| Check | Proves |
|---|---|
| regen-diff | regenerating every env from the spec is a byte-identical no-op |
| terraform validate | every init'ed env validates |
| template-check | the blank template structurally matches the schema |
| platform rules | zero rule errors on spec + tree |
| dependency check | deps.json fresh, ordering valid, ownership registry clean |
| formatting | `terraform fmt -check` on hand-written trees |
| unit suites | workbook round-trip exact, runner logic, artifact export, cost math, log-derivation |

regen-diff is the refactor oracle: the committed `terraform/envs-example`
tree is the captured output of the synthetic example spec, and a customer
workspace's own tree plays the same role there (`lzctl check regen-diff`),
so customer-specific assumptions can't hide.

## 3. Post-apply verification

Re-plan everything after an apply chain; only clean or known-benign diffs
may remain. Anything else means the apply left the estate inconsistent —
stop and investigate before further changes.
