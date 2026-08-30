# Cost estimation: the rate card and its limits [IMPLEMENTATION]

A plan's cost summary exists so the approver sees money, not just resource
counts (assets/plan-triage-drift). It is an **advisory estimate** — it never
gates, and it is wrong in specific, knowable ways. Know them before quoting a
number to anyone.

## The rate card

A flat, per-region `{rate_key: number}` map with a currency and an
hours-per-month convention. Deliberately manual: rates are typed in from the
public calculator or a recent bill. There is no pricing API, no scraper, and
no auto-refresh — a rate card is a snapshot someone maintained.

- **It ships empty.** Every rate is `null` until filled, so an unfilled card
  prices nothing and says so (`RATE NOT SET`). Fill the card for the target
  region before promising a cost line; a GUI plan that never passes a custom
  card will always use the empty default.
- Keys are **string-built from the plan** (flavor names, WAF codes). A flavor
  that is not already a key is silently unpriced rather than an error, so a
  new instance type quietly drops out of the total.
- Keep prices out of the repo when they are contract prices. Public
  list rates in a rate card are fine; customer commercial terms are not
  (platform limits and error codes are shareable, commercials are not).

## What it prices, and what it silently doesn't

Billable types are a hardcoded list (compute + its system disk, block volumes,
EIP bandwidth, NAT, load balancers, backup vaults, VPN gateways, dedicated
WAF, firewall instance, managed database). Anything else in the plan is
non-billable by omission — not by a decision that it costs nothing.

| Blind spot | Effect on the number |
|---|---|
| **Creates only** | in-place `update` (a resize, a bandwidth change) contributes nothing |
| **Deletes not credited** | destroys produce a count-only note, never a negative figure |
| **Billing mode ignored** | everything is priced pay-per-use × hours-per-month, including resources already converted to monthly |
| **Unknown rate keys** | dropped from the subtotal, listed as `RATE NOT SET` |
| **Consumption-based services** | log ingestion/retention, per-attachment and per-GB router traffic, per-workspace security services — none are modelled |

The report prints a **"known subtotal"** — the sum of the items it could
price. Read next to a list of unpriced lines it looks like a total. When
reporting a figure, always say how many items were unpriced.

## Rules

1. **Never present the estimate as a quote.** It is a delta-shaped sanity
   check: "this change adds roughly N of recurring spend", with the unpriced
   count attached. Point at the vendor calculator for anything a customer
   will hold you to.
2. **Cost never gates.** Triage exit classes come from destructive/benign
   analysis alone (assets/plan-triage-drift). A large cost delta is a reason
   for a human to look, not an automatic block.
3. **A monthly-converted estate reads high.** After any console conversion to
   prepaid, the estimator still prices pay-per-use. Read
   assets/billing before reconciling an estimate with a bill.
4. **Design decisions that cost money belong in the spec's guidance, not the
   estimator** — router attachment counts, flow-log volume, per-workspace
   security tooling, and firewall tier are chosen at design time; the
   estimator sees them only after they are already in a plan.
5. **Pin the math with a test.** Hours-per-month, GB-month arithmetic, the
   unpriced path, and the destroyed-resources note are all easy to break
   silently in refactors; a unit suite covering them is part of the
   regression harness (assets/validation-gates).
