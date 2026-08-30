# The handover artifact [RUNBOOK]

## The artifact model

The customer receives a **generated release artifact**, never the working
tree:

- `modules/` + `envs/` with paths rewritten to be self-contained.
- `*.generated.tf` renamed to plain `.tf` names — in the artifact they are
  ordinary hand-maintained Terraform (the customer has no generator).
- Generator-era comments rewritten to operator-facing wording.
- Excluded always: secrets files, state backups, logs, plan files, `.bak`,
  Python tooling, Excel sources.
- Shipped deliberately: the 00-bootstrap LOCAL state (operators cannot
  manage the state bucket without it), one root `.gitignore`.
- `MANIFEST.txt`: sha256 of every shipped file + version + enabled features.
- Release metadata: VERSION, CHANGELOG generated from the spec diff between
  releases (never hand-written). Each release snapshots its spec so the next
  CHANGELOG diffs against it.

Export is profile-driven (per customer: envs directory, feature flags,
target — outputs namespaced per profile so two customers never overwrite
each other) and deterministic — same inputs, same artifact. An oracle test
compares the export against the last shipped artifact and fails on
unexplained diffs.

Caveat the CHANGELOG honestly: it sees **spec-driven changes only**. Hand-
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
3. State backups current; bucket versioning confirmed.
4. Credentials rotated out of delivery hands; customer's own AK/SK proven
   against preflight.
5. Document set regenerated from the shipped state.
6. Cookbooks reviewed against the customer's actual operating model.
7. Acceptance evidence collected (timing + zero-console-steps proof).
