# The skill ↔ pipeline contract

This is the product's core design statement. Everything else in the repo is an
implementation of it.

**The skill decides and asks; the pipeline executes and gates.**

| Concern | Owner | Form |
|---|---|---|
| Judgment: interpreting prose answers, design trade-offs, naming, what to ask the customer | skill (agent or engineer) | edits to files a human can diff |
| Facts: appendix rows, CIDRs, account names | neither — copied verbatim | `lzctl intake` (mechanical dump) |
| Bucketing questions, drafting the neutral spec | pipeline | `lzctl assess` (deterministic, never guesses) |
| Every gate | pipeline | an exit code (`validate` 1 on errors; `build` 3 on unresolved OPEN decisions; `plan` 2/3 on changes/destructive; `apply` typed confirm) |
| Every model-facing surface | pipeline | a file or a CLI — no step depends on a particular model's behavior to be safe |

Consequences, in decreasing order of importance:

1. **No deployable value is generated without an explicit decision.** The assess draft is
   neutral (every value unset, failing validation by design); OPEN questions
   block `build` mechanically until a resolution — who, why — is recorded in
   `lz.spec.<slug>.decisions.json`. The spec's provenance block hash-binds the
   decision set, so the gate survives spec copies/renames and manifest
   truncation alike; the only detachment path is deleting `provenance` from
   the spec — a deliberate, reviewable diff (an audited `detach-lineage`
   command is planned).
2. **Every agent action is a command a human could have typed**, and every
   judgment call lands in an artifact (the decisions files, the spec diff)
   that a human reviews and signs off.
3. **The product works with no model at all**: run the commands by hand, edit
   the spec in the bundled editor (`lz-app`). Model *competence* on the
   judgment steps is a separate, measured question — `tests/evaluation/`.
4. **The handover receiver needs none of this.** The generated estate is
   plain HCL operable with just the runner (`lzctl`) — no pipeline, no skill,
   no AI (the handover rule: logic lives in codegen, not in HCL).

The phase graph that sequences all of this is machine-readable at
`schemas/phases.json` and rendered in `docs/workflow.md`; the skill's Phase
contract table mirrors it.
