# Intake: questionnaire → draft spec [IMPLEMENTATION]

The stage before design. An open-ended questionnaire the customer fills
**alone**, converted into a draft spec plus an explicit list of what is still
unknown. The output is not a buildable config — it is a starting point plus a
workshop agenda.

## The instrument is generated from the schema

The question catalogue is source of truth; the workbook is a rendering of it.
A coverage check runs at generation time and **fails the build** when:

- a schema table is reachable from no question (a new table forces a new
  question, or an explicit exemption), or
- a question's wiring names a table that no longer exists (typo or drift).

Exemptions are a hand-curated list, each with a stated reason — fixed enums,
service-to-service plumbing, derived-from-topology tables, reserved tables.
Stale exemptions (an entry whose table is gone) are errors too, so the
exemption list cannot rot. Consequence: a stale questionnaire cannot exist
silently. Regenerate it after any schema change.

## The hidden wiring sheet is the contract

Every question carries, in a hidden sheet that travels inside the file the
customer returns: its ref, tier, category, machine targets
(`Sheet.Table[.field]`), and its `default_if_silent`. Plus a meta row stamping
the questionnaire and schema versions.

The filled workbook is therefore self-describing — the converter never needs
to know which version generated it, and version skew cannot silently
mis-route an answer.

## Structured facts belong in appendices, and are copied verbatim

Prose is for intent; rows are for facts. Give the customer plain tables for
the things that must survive conversion exactly — accounts/environments, the
IP plan, teams and access. Then:

**Never retype or "normalize" a CIDR, IP, email, account name, or team
name.** Copy appendix rows verbatim from the extraction. Retyping is how a
prefix length or a digit changes between the customer's plan and the estate.

Anything larger than a table (a communication matrix, an existing rule dump)
is requested as an attachment in the question guidance — a document beats
retyping.

## Extraction and interpretation are separate steps

- **Extraction** is mechanical and deterministic: read the workbook, emit
  answers + wiring + appendix rows as data. No judgement, no NLP.
- **Interpretation** is the agent's job, and only it: map prose to the wired
  targets, conservatively.

Keeping them apart means the ambiguous half is reviewable and the exact half
is not at risk.

## Every field lands in exactly one of three buckets

| Bucket | Meaning | Recorded where |
|---|---|---|
| ANSWERED | the customer's response supplies it | the draft spec |
| DEFAULTED | the source is silent and a documented, authorized default exists (`default_if_silent`) | *Defaults applied* in the decisions file |
| OPEN | the value is required and no authorized default exists | *Open questions*, citing the question ref |

**Never invent a value.** A missing CIDR, email pattern, or retention number
is a decisions-file entry, not a guess — a guess is indistinguishable from a
fact once it is in the spec. "Unknown" and "no requirement" are valid customer
answers; treat both as signal.

## Conversion rules

- Start from the **neutral draft `lzctl assess` writes** — every table empty,
  every scalar null — and interpret answers into it with `lzctl set`. Consult
  the example spec for STRUCTURE (field shapes, row layouts) only; its values
  are one fictional customer's and must never leak into a draft. Defaults you
  apply are the documented `default_if_silent` ones, recorded as DEFAULTED
  decisions so they are reviewed, not invented.
- **Sweep cross-references** after replacing accounts, VPCs, or groups —
  example rows that referenced the old names (log-convergence targets, audit
  exclusions, security groups, account assignments, SNAT/DNAT) are now
  dangling. Rebuild or empty them; referential integrity is enforced
  downstream and will list every miss.
- **No secrets in the spec — and never re-emit one.** A pre-shared key or
  credential pasted into an answer stays out of the spec; write a placeholder
  and flag it for out-of-band handover. Do not quote the pasted value back in
  any output either — transcripts and logs are also channels; refer to it as
  "the pasted value".
- Stamp provenance on the draft: which questionnaire version and which source
  file it came from.

## Gates before this draft becomes an estate

1. Spec validation must pass with **zero errors**; warnings go into the
   decisions file rather than being silently accepted.
2. A human walks the decisions file with the draft loaded in the editor.
3. Only then does it reach build/plan (assets/validation-gates).

Zero errors is necessary, not sufficient — validation proves the spec is
well-formed and self-consistent, never that it is what the customer meant.

## Sizing

Huawei CAF defines three planning modes — full-scale, standard, and minimal
IT-management account sets. Ask which mode fits during intake instead of
assuming the full set; the questionnaire's account-appendix rows decide the
actual set.
