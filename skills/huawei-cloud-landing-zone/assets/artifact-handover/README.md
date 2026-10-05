# The handover artifact [RUNBOOK]

## The artifact model

The customer receives a **generated release artifact**, never the working
tree:

- `modules/` + `envs/` with paths rewritten to be self-contained.
- `*.generated.tf` renamed to plain `.tf` names — in the artifact they are
  ordinary hand-maintained Terraform (the customer has no generator).
- Comments already follow the artifact convention; the export runs
  `comment_lint` over the assembled tree and refuses one that breaks it.
- Excluded always: secrets files, every `*.tfstate*` (state in any
  spelling), state backups, logs, plan files, `.bak`, Python tooling, Excel
  sources.
- The 00-bootstrap LOCAL state is **never** in the artifact. Operators
  cannot manage the state bucket without it, so hand it over out of band
  (an encrypted transfer to the customer's operator, recorded in the
  handover checklist) and have them store it outside the repository.
- Shipped deliberately: one root `.gitignore` (lock files stay tracked).
- Curation per profile: `skip_envs` (env dirs not shipped, also dropped
  from `deps.json`), `ship_markdown` (default true), and library modules no
  shipped env references are pruned automatically.
- `MANIFEST.txt`: sha256 of every shipped file + version + enabled features.
- Release metadata: VERSION, CHANGELOG generated from the spec diff between
  releases (never hand-written). Each release snapshots its spec so the next
  CHANGELOG diffs against it.

Export is profile-driven (per customer: envs directory, feature flags,
target — outputs namespaced per profile so two customers never overwrite
each other) and deterministic — same inputs, same artifact. An oracle test
compares the export against the last shipped artifact and fails on
unexplained diffs.

State the CHANGELOG limitation clearly: it sees **spec-driven changes only**. Hand-
written envs outside the pipeline ship in the artifact but never appear in
the generated CHANGELOG — record those changes manually.

## Comment hygiene (standing rule)

Shipped HCL carries only concise block descriptions — what a block is and,
in one line, what it does. Lessons, live-API quirks, error codes, dates,
"confirmed" notes, and historical rationale live in an INTERNAL engineering
notes file outside every export path, anchored by file + resource. Also keep
customer identifiers out of shared module trees — module comments ride into
every profile's export, including other customers'.

## Handover checklist (gate before the customer takes the keys)

1. Artifact exported from a clean verify run; manifest checksums match.
2. All envs plan clean or known-benign against live.
3. State backups current; bucket versioning confirmed; the 00-bootstrap
   local state handed over out of band.
4. Credentials rotated out of delivery hands; customer's own AK/SK proven
   against preflight.
5. Document set regenerated from the shipped state.
6. Cookbooks reviewed against the customer's actual operating model.
7. Acceptance evidence collected (timing + zero-console-steps proof).
