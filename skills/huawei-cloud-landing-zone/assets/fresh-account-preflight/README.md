# Fresh-account preflight [RUNBOOK]

A fresh tenant is not a small version of a mature one. Several things that
always work on an established account **do not exist yet** on a new one, and
they fail mid-apply rather than at plan. Check these before the Day-1 chain,
not during it.

## Things that do not exist until something creates them

- **Service-default encryption keys.** The default key for a service
  (`<service>/default`) materializes on first use through the console, not on
  account creation. On a fresh account the key list is genuinely empty, so a
  data source looking one up fails. Either create the key explicitly or make
  the lookup conditional. *Blocks the observability/security envs.*
- **Agencies and grants are asynchronous.** An authority grant (enterprise
  projects, a freshly created agency) propagates after the API returns
  success. A resource created seconds later fails with a permission error on
  an account that genuinely has the permission. *Blocks the earliest envs.*
  Retry-once on this class is correct behavior, not a workaround
  (assets/apply-orchestration).

## Capacity is per-AZ and per-flavor, and it is not a quota

"Resource not enough" is a **stock** answer, not a limit you can raise: the
AZ you hard-coded does not carry the flavor you asked for. Never hard-code an
availability zone for a flavored resource — resolve the AZ from a data source
filtered by the flavor *and* the attachment type, and let the platform pick a
zone that stocks it.

## The one hard quota that shapes design

Service control policies cap at **5 attached per entity, including the system
FullAccess policy** — four usable slots, with a per-document character limit.
This is a design constraint, not a preflight check: guardrails must pack into
combined documents before they are ever applied (assets/scp-guardrails).

## Known gap: there is no live quota preflight

Counting headroom before an apply — address counts, compute cores, network
and router attachment limits — **is not implemented**, and the numbers are
not documented here because they have not been hit and confirmed. The
consequence is honest and specific:

- A quota wall surfaces **at apply**, partway through an env, leaving that env
  half-applied and the chain stopped.
- Recovery is ordinary: raise the limit with the provider, then re-run the
  same env — applies are resumable because state is written as resources are
  created (assets/apply-orchestration).

**Do not invent quota numbers.** If a headroom figure matters to a
commitment, get it from the tenant's own console or a support response and
record it with the account, not in reusable doctrine. Only limits confirmed
against the live platform belong in the constraint list.

## Preflight checklist before a Day-1 chain

| Check | Why |
|---|---|
| Credentials + backend reachable, checksum env vars set | the state backend fails silently without them (assets/state-backend) |
| Region supports every service in the spec | service availability is regional, not global |
| Default encryption keys exist (or lookups are conditional) | empty on a fresh tenant |
| No hard-coded AZs for flavored resources | AZ stock varies |
| Guardrails pack within the policy cap | otherwise the perimeter env cannot attach |
| Dependency graph fresh, envs in numeric order | later envs read earlier outputs |
| Retry-once configured for known transients | async grants are normal, not errors |
