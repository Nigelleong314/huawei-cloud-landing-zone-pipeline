# Discovery protocol for ad-hoc requirements [DOMAIN]

The intake questionnaire (assets/intake-questionnaire) handles the formal
path. This asset covers everything else: a request arriving as chat, email,
or a one-line ticket whose spec-relevant facts are incomplete. "Create
production and development VPCs" names no region, no CIDRs, no account
placement, no connectivity, no egress, no DNS, no security posture — seven
design decisions hiding in six words.

## The rule

**Identify what is missing and ASK. Never invent a critical infrastructure
value** — a CIDR, region, account, name, retention period, or exposure
decision. An invented value is indistinguishable from a requirement once it
is in the spec, and CIDRs and names are effectively permanent
(rename = destroy/create — see assets/state-surgery).

## Required facts per domain

Walk this table before designing. Each row is a question to the requester,
not a value to guess.

| Domain | Must know before designing |
|---|---|
| Accounts/OU | Which account does this land in? Environment separation (prod/dev split = separate accounts or same)? New account or existing? |
| Network | Region. CIDR — and **who owns the IP plan** (a self-chosen CIDR that collides with on-prem is unfixable). Subnet layout. ER attachment or isolated? Internet ingress? Egress path (central NAT or none)? DNS (hub resolver or default)? |
| Identity | Who accesses it, via which groups / permission sets? |
| Security | Exposure (internet-facing or internal only)? Firewall rules — both directions, not just inbound. Logging destination. |
| Cost | Which enterprise project? Mandatory tags present? |
| Deployment | Which env does it land in, and does it disturb apply order (assets/apply-orchestration)? |

## Every fact lands in one of three buckets

Mirroring assets/intake-questionnaire:

| Bucket | Meaning | Recorded where |
|---|---|---|
| ANSWERED | requester supplied it | the spec |
| DEFAULTED | the source is silent and a documented, authorized default exists | *Defaults applied* in the decisions file |
| OPEN | the value is required and no authorized default exists | *Open questions* in the decisions file |

## When the requester insists on proceeding with OPEN items

Proceed only with each assumption **written into the decisions file** as an
explicit line item ("assumed 10.x.y.0/24 — unverified against the IP plan,
owner: <requester>"). Never resolve an OPEN item silently; a silent
assumption surfaces later as an outage or a re-IP project.
