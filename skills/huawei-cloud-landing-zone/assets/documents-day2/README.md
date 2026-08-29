# Generated documents and Day-2 operations [REUSABLE]

## Document set (all generated from tfvars + state, never hand-written)

| Document | Source | Notes |
|---|---|---|
| IP management workbook | tfvars CIDRs | free/allocated/reserved blocks, per-subnet rows |
| Build configuration book | tfvars + pulled state | as-built values incl. live IDs when state is supplied; hand-authored HCL outside the pipeline does NOT appear — patch those sections deliberately |
| Handover checklist | tfvars + pulled state | requires a state pull to be meaningful |
| Excel LLD workbook | the spec | round-trip verified: workbook re-imports to the identical spec |

## LLD / spec contract

- The Excel workbook is the human-facing contract: sheets in apply order,
  three table kinds (scalar / list / object), sentinel-delimited tables,
  sample rows, dropdown validations — all generated from the schema.
- The JSON spec is canonical; the workbook is an artifact of it. A customer
  can still hand-edit the workbook and re-import (round-trip gate).
- When migrating workbook layouts in place, never structurally insert rows
  above merged ranges (they don't shift) — append or use blank-row patterns.

## Handover documentation overlay

- Per-env READMEs (what the env does, its inputs, its outputs).
- Cookbooks for the changes operators actually make: add an account, add a
  spoke VPC, add a VM, DNS changes, firewall changes, governance changes,
  security-group changes, state safety, general operations.
- Operationally sensitive facts get cookbook coverage (e.g. VPN gateway
  public EIPs are create-only: changing them force-replaces the gateway =
  new public IPs = site down until the far end reconfigures).

## Day-2 operations model

- All changes flow spec → validate → build → plan → triage → apply; the
  runner enforces order, locking, backups.
- Drift sentinel on a schedule; known-benign list keeps the signal clean.
- **The escape-hatch env pattern**: a customer-specific workload env may be
  added OUTSIDE the pipeline — hand-written plain HCL with its own local
  modules, resolving upstream names via data sources, registered only in
  `deps.json`. This is the documented manual-extension path and the proof
  the handover promise holds; keep such envs deliberately out of the
  schema/builders so the product pipeline stays generic.
- Acceptance benchmark [ADAPTABLE]: fresh-account deployment in under
  30 minutes wall-clock with zero manual console steps, repeated across
  three consecutive runs, evidenced via CTS.
