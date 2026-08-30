# Identity [DOMAIN]

## Structure

- Identity Center: groups → permission sets → account assignments. IAM
  baseline (login/password policy) fans out per account.
- App-level permission sets: full-management access scoped by
  `g:EnterpriseProjectId` conditions to enterprise projects looked up by
  name in the owning account. Emit these at env level — the EP lookup needs
  that account's provider.
- Scoping construction: Allow service wildcards + Deny per-resource entry
  gates conditioned on `ForAnyValue:StringNotEqualsIfExists` /
  `g:EnterpriseProjectId`.

## Policy-language quirks (v5 identity policies)

- **`StringLike` / `StringNotLike` are SUBSTRING matches** on this platform —
  they do not support `*` wildcards. Use `StringMatch` / `StringNotMatch`
  for wildcard patterns. A policy ported from AWS semantics silently matches
  the wrong set.
- **Preserve `IfExists` suffixes** when editing conditions. Dropping
  `...IfExists` turns "deny when the key is present and wrong" into "deny
  whenever the key is absent", which breaks APIs that legitimately omit the
  key.
- v5 identity resources (`/v5/*` APIs, e.g. trust agencies) only work
  through an `assume_role`-block provider — the agency-token mode fails with
  `PAP5.0046` (see assets/cross-account).

## Break-glass and identity lifecycle

- **Break-glass model per Huawei CAF**: member-account root users are
  constrained by SCP deny (assets/scp-guardrails); the master-account root
  credential is held **offline by a named senior owner** (CIO / IT-director
  class). Document WHO in the LLD — never in code or the spec.
- **Emergency access** = one native IAM admin user per critical account:
  monitored, rarely used, with **alarm-on-login** wired via CTS/CES to the
  observability topics (assets/observability). Test the path quarterly —
  an untested break-glass account is a locked door with a lost key.
- **Identity lifecycle**: joiners and leavers flow through the IdP + SCIM
  only — no local users. Leaver deprovisioning is **verified by listing
  account assignments**, not assumed from the IdP disable.
- **Permission-set changes are spec changes** — auditable, reviewed,
  applied through Terraform. Console edits to permission sets are drift
  (assets/plan-triage-drift), not administration.
