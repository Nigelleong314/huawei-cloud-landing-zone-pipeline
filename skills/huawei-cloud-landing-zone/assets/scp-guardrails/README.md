# SCP guardrails [PLATFORM]

## The guardrail set (v5.0 only)

deny-leave-org, deny-root-user, deny-unauthorized-RAM-share,
deny-unauthorized-RMS-aggregation, require-mandatory-tags, deny-public-OBS,
protect-CTS-tracker, deny-outside-allowed-region, require-tag-keys.

## Packing under the 5-policy cap

- Huawei caps attached SCPs at **5 per entity** (including the system
  FullAccess, which takes one slot) — pack guardrails into combined
  documents (one Deny statement each), under the 5,120-char per-document
  limit.
- An `enforce` flag routes each statement to the LIVE (attached) document or
  a STAGED unattached document — staging is how new guardrails are reviewed
  without enforcement.
- Tag-governance guardrails (require-mandatory-tags, require-tag-keys) get
  their **own document**, separate from the general one.

## Tag SCP construction (the part everyone gets wrong)

- `require_mandatory_tags` must emit **one Deny statement per tag**: Huawei
  ANDs keys within a statement, so a single statement only denies
  fully-untagged creates; separate statements OR together into "deny if ANY
  tag missing".
- Its action list may contain **only create APIs that accept tags in the
  request**. OBS buckets and the VPC family (vpcs/subnets/securityGroups)
  tag AFTER create — listing them denies ALL creation (`SYS.0403`), even
  with provider default_tags and resource tags set (confirmed live). Cover
  those services with detective Config/RMS rules instead.
- `require_tag_keys` denies creates whose request tag keys fall outside an
  approved set (`g:TagKeys`, case-sensitive).

## Tenant and rollout quirks

- **SCP service codes are tenant-variable**: the published catalogue lists
  codes some tenants reject (e.g. `bss`, `dew`) — ship only live-confirmed
  codes as defaults.
- CTS: one org tracker (region hard-coded), audit bucket + KMS, per-account
  minimal trackers for accounts excluded from central transfer.
- **Perimeter enforcement (deny-public-OBS etc.) defaults OFF** until every
  spoke VPC has its OBS VPC endpoint — enabling early locks the org out of
  its own state bucket.
- Native SCP dry-run preview is not used (it needs an OBS reports bucket
  plus an Organizations trust agency); staged documents fill that role.

## Staged rollout and the sandbox pattern

Huawei CAF prescribes testing control- and data-perimeter policies in a
**sandbox account** before org-wide attachment. This framework's
staged/unattached-document mechanism (`enforce = false`) is the **code-side
half** — the policy text exists, reviewed, unattached. The sandbox-account
test is the **process-side half**: attach to the sandbox, exercise the
denied operations, then promote. Neither half substitutes for the other.
Perimeter enforcement (e.g. deny-public-OBS) flips on only after every
spoke has its VPC endpoint — the review gate for that flip is in
(assets/plan-triage-drift).
