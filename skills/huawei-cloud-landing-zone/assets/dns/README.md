# DNS: the hub-resolver pattern [REUSABLE]

## Pattern

Private-zone VPC association is same-account only (the provider has no zone
sharing). So: point every hub+spoke subnet's DHCP at the inbound resolver
endpoint IPs; associate resolver rules to the resolver VPC. One DNS env owns
zones, records, endpoints, and query logging.

## The unattached-spoke black-hole (silent failure)

The hub resolver is only reachable **over the ER**. Pointing an UNATTACHED
spoke's subnet DHCP at the resolver endpoint IPs black-holes ALL DNS in that
VPC — not just internal names, since every query goes to an unreachable IP.

- Gate subnet `primary_dns`/`secondary_dns` on the spoke's ER attachment
  being enabled. Left unset, the provider applies the region's built-in
  private resolver at CREATE, so an isolated spoke still resolves public
  names.
- **The guard cannot repair already-deployed subnets**: the DNS attributes
  are Optional+Computed, so a null in config means "keep the current value" —
  Terraform reports no changes and never self-corrects. The provider only
  supplies the regional default on CREATE; the update path forwards the
  empty config value and does not re-derive. Repair an existing black-holed
  subnet out of band (console/API, set the regional resolver); because
  config is null and the attribute is Computed, Terraform then adopts the
  live value permanently with no drift.

## Composition rule

The DNS query-log LTS group/stream belong to the observability env (created
and converged there); the DNS env attaches the resolver access log to them
without managing the infrastructure — a fresh deploy stays strictly one
ordered pass.
