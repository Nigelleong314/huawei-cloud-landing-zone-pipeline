---
name: questionnaire-to-spec
description: Convert a filled LZ Assessment Questionnaire (xlsx) into a draft lz.spec.<customer>.json plus a decisions-needed list. Use when the user provides a completed assessment questionnaire or asks to turn questionnaire answers into a spec.
---

# Questionnaire → draft spec

Input: a filled `HuaweiCloud-LZ-Assessment-Questionnaire.xlsx` (any path) and a
customer slug (lowercase, e.g. `acme`). Ask for the slug if not given.

Output: `lz_spec/lz.spec.<slug>.json` (draft) + `lz_spec/lz.spec.<slug>.decisions.md`.

This skill applies the huawei-cloud-landing-zone skill's intake doctrine (assets/intake-questionnaire, assets/discovery-protocol); load that skill alongside.

## Steps

1. **Dump, never read the xlsx ad hoc:**
   `py lz_pipeline/tools/dump_questionnaire.py <filled.xlsx> -o <jobtmp>/dump.json`
   The dump has every answer joined to its wiring `targets`
   (`Sheet.Table[.field]` in `lz_spec/schema.py` terms) and `default_if_silent`.

2. **Start from the defaults baseline:** load `lz_spec/lz.spec.example.json`,
   keep its structure, replace example values as answers dictate. Read
   `lz_spec/schema.py` for field meanings when a target is unfamiliar.

3. **Apply answers:**
   - **Appendix rows are facts — copy VERBATIM from the dump JSON.** Never
     retype or "normalize" CIDRs, IPs, emails, account or team names. Rows
     map near-1:1: Appendix A → `01_Foundation` accounts/OUs, B → `05_Network`
     CIDR tables + `spoke_private_supernet`, C → `03_Identity` groups/users/
     permission sets/assignments.
   - **Prose answers are interpreted** against their `targets`. Derive
     conservative values; guidance-stated defaults are the fallback.
   - **Unanswered questions** take `default_if_silent`; note each applied
     default in the decisions file (customers review defaults, not archaeology).
   - **Never invent facts.** A value the spec needs that no answer provides
     (a CIDR, an email pattern, a retention number) is a decisions-file entry
     citing the question ref (e.g. C16), not a guess.
   - **Sweep cross-references.** Replacing accounts/VPCs/groups invalidates
     every example-spec row that references the old names (e.g.
     `AuditSettings.cts_no_transfer_accounts`, `LogConverge`, `11_SGACL`
     SecurityGroups, AccountAssignments, SNAT/DNAT rows). Rebuild them for the
     new names or empty them — `spec-validate` enforces referential integrity
     and will list what you missed.

4. **Secrets:** never write real credentials/PSKs into the spec. VPN PSK
   fields get `REPLACE_WITH_STRONG_PSK`. If the customer pasted a secret into
   an answer, leave it out of the spec and flag it in the decisions file.

5. **Stamp the spec:** `customer: "<slug>"`,
   `source: "assessment questionnaire v<questionnaire_version> (<source_file>)"`,
   keep `format`/`schema_version` from the example spec.

6. **Validate** (must pass with 0 errors; warnings go into the decisions file):
   `py -m lz_pipeline spec-validate lz_spec/lz.spec.<slug>.json`

7. **Decisions file** (`lz.spec.<slug>.decisions.md`): three short sections —
   *Open questions* (missing facts, with question refs), *Defaults applied*
   (silent deep-dive defaults worth confirming), *Follow-ups* (attachments
   referenced but not provided, secrets to hand over out-of-band). This file
   is the gap-fill/workshop agenda.

8. **Report:** answered/total count, what was drafted, validation result, and
   that the draft is reviewable in the app (`py -m lz_app` → spec dropdown).

The draft is a starting point for engineer review — it does not go to
`build_envs`/plan until a human has walked the decisions file.
