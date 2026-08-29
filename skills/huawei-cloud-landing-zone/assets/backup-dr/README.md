# Backup and DR [REUSABLE]

## CBR is a Day-1 spec item, not an afterthought

Cloud Backup and Recovery (CBR) vaults and policies are spec-driven and
deployed with the estate:

- **Vault sizing** is a spec field per vault (GB). Undersized vaults stop
  backing up silently when full — size for retention × change rate, not
  current disk usage.
- **Backup policy** schedule and retention are spec fields (cron-style
  trigger times, retention count/days). Policy → vault → resource binding
  all in Terraform.
- What stays in the spec: vault size, policy schedule, retention, which
  resources bind to which vault. What stays out: one-off manual restore
  operations — those are Day-2 console/API actions, never Terraform.

## Billing interactions (design decisions, not billing toggles)

Reference assets/billing before touching vault billing:

- **Auto-expanding vaults cannot be converted to prepaid.** Auto-expand is
  a postpaid-only feature — choosing yearly/monthly billing means choosing
  fixed size, and someone must then watch capacity.
- **Freezing a near-full vault's size breaks its backups within days.**
  Converting to prepaid at current size is a time bomb; resize first, then
  convert. This is a design decision to record in the decisions file, not a
  BSS toggle.

## OBS lifecycle tiering for archives

Archive/log buckets get lifecycle rules in the spec:

- Transition to cold (and deep-archive where available) tiers **by age** —
  spec fields for the day thresholds.
- Always include **abort-incomplete-multipart** cleanup — orphaned multipart
  uploads bill forever and are invisible in the console object listing.
- Expiration (delete-by-age) is a retention decision: it goes through the
  decisions file, never defaulted.

## State backup ≠ data backup

The runner's `terraform state pull` backup before every apply
(assets/state-backend) protects the **IaC state**, nothing else. CBR
protects **workload data**. Neither substitutes for the other; a handover
that mentions only one is incomplete.

## DR honesty

Cross-region DR (replicated vaults, standby regions, failover runbooks) is
a design decision this framework **records but does not automate** in v1.
If the customer requires it: capture the requirement and target region in
the decisions file, state plainly in the handover what is NOT covered, and
scope the automation as follow-on work. Never imply DR exists because
backups do.
