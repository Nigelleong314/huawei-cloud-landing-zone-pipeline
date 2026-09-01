---
name: questionnaire-to-spec
description: Convert a filled LZ Assessment Questionnaire (xlsx) into a draft lz.spec.<customer>.json plus a decisions file the build gate enforces. Use when the user provides a completed assessment questionnaire or asks to turn questionnaire answers into a spec.
---

# Questionnaire → draft spec

Invocation: `/questionnaire-to-spec <filled.xlsx> customer=<id> [workspace=<dir>]`
(or any natural-language request that provides a filled questionnaire).

Input: a filled `HuaweiCloud-LZ-Assessment-Questionnaire.xlsx` (any path) and a
customer ID (lowercase, e.g. `acme`). **Inference rule:** take the workbook
from an explicitly attached file, an explicit path, or exactly one unambiguous
matching artifact in the workspace — ask only when multiple candidates exist.
Ask for the customer ID whenever it cannot be established safely; never
derive it from guesswork.

Output, under `<workspace>/specs/`:
- `lz.spec.<customer>.json` — the draft (starts NEUTRAL: every value unset)
- `lz.spec.<customer>.decisions.md` — human-readable decision agenda
- `lz.spec.<customer>.decisions.json` — machine-readable; **`lzctl build` refuses
  to run while it contains OPEN items without a recorded resolution**

This skill applies the huawei-cloud-landing-zone skill's intake design rules
(assets/intake-questionnaire, assets/discovery-protocol); load that skill alongside.

**The contract: you decide and ask; the pipeline executes and gates.** Facts
are copied verbatim by `lzctl intake`; classification and the neutral draft come
from `lzctl assess`; your judgment lands only in reviewable artifacts (the
spec diff, decision resolutions) — never in bypassed gates.

## Steps

1. **Intake (mechanical, no interpretation):**
   `lzctl intake <filled.xlsx> -o <jobtmp>/dump.json`
   The dump has every answer joined to its wiring `targets`
   (`Sheet.Table[.field]`) and `default_if_silent`.

2. **Assess (deterministic, never guesses):**
   `lzctl assess <jobtmp>/dump.json --customer <customer> --workspace <workspace>`
   This writes the three outputs above. The draft is a schema-shaped skeleton
   with every table empty and every scalar blank — it FAILS `lzctl validate`
   until you interpret answers into it. That failure is the design: no
   deployable value exists that nobody decided.

3. **Interpret answers into the draft** (your job — the only step with judgment):
   - **Appendix rows are facts — copy VERBATIM from the dump JSON.** Never
     retype or "normalize" CIDRs, IPs, emails, account or team names. Rows
     map near-1:1: Appendix A → `01_Foundation` accounts/OUs, B → `05_Network`
     CIDR tables + `spoke_private_supernet`, C → `03_Identity` groups/users/
     permission sets/assignments.
   - **Prose answers are interpreted** against their `targets`. Consult the
     packaged `example.spec.json` for field shapes and `schema.py` for
     meanings — copy STRUCTURE from the example, never its values.
   - **Resource names are inferred, not asked one by one.** Derive every
     resource `Name`-class value (VPCs, subnets, EIPs, NATs, buckets, vaults,
     log groups, endpoints, ...) from the customer's stated naming convention,
     applied consistently across all sheets; honor service limits (bucket
     names lowercase + globally unique). No stated convention → use the
     question's documented default pattern and record the convention as a
     DEFAULTED item so the customer reviews it once, not per resource. Names
     are proposals — a name the customer wrote explicitly (any appendix row)
     stays verbatim and is never "normalized" to the pattern.
   - **Enterprise-project and tag design are inferred the same way.** Derive
     the EP layout (`02_Finance.CostCenters` rows + `AppPermissionSets`
     scoping) from the workload/environment/cost-allocation answers, and the
     tag plan — key naming, `Global.MasterDefaultTags`, `TagPolicies` /
     `MandatoryTags` entries — from the tagging answer, keeping tag keys and
     EP names consistent with the resource-naming convention. Each inferred
     design lands as ONE reviewable DEFAULTED item (the layout / the key
     set), not one per resource.
   - **DEFAULTED items** (silent with a documented `default_if_silent`):
     apply the stated default to the draft. They never block the build, but
     the customer reviews them via the decisions .md.
   - **OPEN items — never invent facts.** A value the spec needs that no
     answer provides (a CIDR, an email pattern, a retention number) stays
     unset in the draft. It is resolved only by editing its entry in
     `lz.spec.<customer>.decisions.json`:
     `"resolution": {"status": "ANSWERED", "approved_by": "<person>", "reason": "<the obtained answer>"}`
     (or `"ACCEPTED_DEFAULT"` when the customer signs off on a proposed
     default). Record who decided — the gate exists so this is auditable.
     **Only `resolution` fields are editable**: the decision set itself is
     hash-bound into the spec's `provenance` block (its origin record), so deleting or altering an item
     (or the whole list) blocks `build` exactly like leaving it unresolved.
   - **Sweep cross-references.** Accounts/VPCs/groups you add invalidate any
     row referencing names that don't exist — `lzctl validate` enforces
     referential integrity and lists what you missed.

4. **Secrets:** never write real credentials/PSKs into the spec. VPN PSK
   fields get a reference (`secret://...`) or a `REPLACE_WITH_...` placeholder
   — platform rule LZR-027 is an **error** on any literal-looking PSK. If the customer
   pasted a secret into an answer, leave it out of the spec, flag it in the
   decisions file, and never re-emit the pasted value anywhere.

5. **Validate** (must pass with 0 errors; warnings go into the decisions file):
   `lzctl validate <workspace>/specs/lz.spec.<customer>.json`

6. **Report:** answered/defaulted/open counts, what was interpreted, which
   OPEN items still block the build, validation result, and that the draft is
   reviewable in the app (`lz-app` → spec dropdown).

The draft does not build until (a) validation is clean AND (b) every OPEN
item in `lz.spec.<customer>.decisions.json` carries a resolution — `lzctl build`
enforces (b) mechanically with exit code 3.
