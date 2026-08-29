# Plan triage, drift, review gates [REUSABLE]

## Plan triage (before every apply)

Classify every resource change in the plan JSON:

- **Destructive** (delete/replace of protected types: VPN gateways, CFW,
  org accounts, state buckets…) → exit 3, blocked without explicit
  allow-destroy approval.
- **Known-benign** (documented permadrifts) → exit 2 with "benign (known)"
  label; safe to proceed.
- **Everything else** → exit 2, human reviews the plan summary.

Include a cost summary (billable resource deltas priced from a rate card) so
the approver sees money, not just resources.

## Drift detection (scheduled + on demand)

- Re-plan each env read-only; classify diffs with the same triage rules.
- Maintain a **known-benign drift list with root causes**, e.g.:
  - ICMP firewall rules: the API never echoes ports → one permanent
    cosmetic diff per rule. Do not chase.
  - Resolver endpoint IP ordering: the API reorders lists.
  - Action-style resources (advanced IPS toggles): server-side state,
    no provider drift tracking; re-apply reasserts.
  - APIs that canonicalize list order (e.g. firewall rule address lists,
    ascending) — keep spec lists in canonical order to avoid permadrift.
- Drift found ≠ failure: report, open an issue, never auto-apply.

## Review gates (human approval points)

| Gate | Trigger | Approver sees |
|---|---|---|
| Design sign-off | before first build | architecture doc + spec |
| Destructive plan | triage exit 3 | the exact resources destroyed/replaced |
| Real apply | any non-dry-run | plan summary + cost delta |
| Billing conversion | any charging_mode change | it's a purchase — console-first rule (assets/billing) |
| Perimeter enforcement flip | enabling deny-public-OBS etc. | VPCEP coverage proof for every spoke |
| Handover | artifact export | manifest + checklist + acceptance criteria |
