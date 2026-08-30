# CI credentials: OIDC → short-lived keys [PLATFORM]

The target model: the pipeline proves its identity with an OIDC token minted
by the CI platform, exchanges it for **short-lived** cloud credentials, and
applies. No long-lived access keys exist in the CI system, and **the agent
never holds credentials at all** — it composes and validates; a separate,
credentialed job applies.

## The chain

```
CI OIDC token → IAM id-token exchange → <ci-deploy-agency> (one account)
              → per-member org agency (second hop) → cloud APIs
```

Federation lands you in **one** account — the one whose domain the identity
provider is registered in. Reaching member accounts is a **second hop**
through each member's organization-access agency, which the platform
auto-creates per member (assets/cross-account). Do not try to federate
directly into every member account.

Because Terraform cannot `for_each` providers, the fan-out is one provider
alias per target account, generated (assets/repo-codegen).

## What the provider actually does

Two API hops, both inside the provider:

1. **id-token exchange** — POST the token to the IAM id-token endpoint with
   the identity-provider id in a header; a subject token comes back in a
   response header.
2. **agency assume** — POST to the v5 agency-assume endpoint with an agency
   URN built from the domain id and agency name; returns access key, secret,
   and a **security token**.

Configuration (an `assume_role_with_oidc` block, or purely environment
variables — the provider takes the OIDC path as soon as the identity-provider
id variable is non-empty, so the block need not appear in HCL at all):

| Field | Note |
|---|---|
| `agency_name` | the CI deploy agency |
| `domain_id` | the account/**domain ID, not the name** — a frequent mix-up |
| `idp_id` | the registered identity provider's name |
| `id_token` / `id_token_file` | exactly one; the file is what a CI runner writes |
| `duration` | seconds; **see below** |

### The TTL is not what you think

The provider's 12-hour default duration applies to the *non-OIDC* assume
path. On the OIDC path, TTL comes **only** from an explicit `duration`. A
"30-minute credentials" policy is therefore a design target that must be
written down as `duration = 1800` — omit it and you inherit whatever the
platform defaults to, silently.

## Day -1: the trust setup is real infrastructure

Registering the identity provider and creating the deploy agency happens
**before** any landing-zone env can run, and it is routinely mis-scoped as
"one manual step". It is an identity provider, its access config, an agency,
and an agency policy. Codify it as a bootstrap env so it is reviewable and
reproducible, or it becomes tribal knowledge that blocks the next engagement.

- **Identity provider**: protocol `oidc`; the provider URL must equal the
  `iss` claim in the token; a client id; and a **signing key as a JWKS
  document**. Access type is programmatic-only or programmatic+console (the
  latter also needs an authorization endpoint and scopes including `openid`).
- Limits worth knowing before design: a small per-account cap on identity
  providers, and OIDC providers support **virtual-user SSO only**. The
  resource's id is its name.
- **Trust agency (v5)**: its trust policy is a Required, **ForceNew** JSON
  document — changing the trust relationship replaces the agency. Statements
  are v5 (`"Version": "5.0"`) and the assume action is
  `sts:agencies:assume`. Attach permission policies by name; keep them
  minimal — this principal can deploy the estate.

## When the exchange is rejected

Failures surface at hop 1, before Terraform does anything recognizable, so
read the error from the id-token exchange rather than the plan output.
Check in this order:

1. **Token signing.** The identity provider registration holds a **JWKS**,
   which can only carry asymmetric public keys. A token signed with a
   symmetric algorithm (HS256) has no public key to register and cannot be
   validated — the CI platform must issue asymmetrically signed (RS256-style)
   tokens. This is the trap when a hand-rolled or test token works locally
   and nothing works in the pipeline.
2. **`iss` mismatch** between the token and the registered provider URL.
3. **Audience/client id mismatch** — the CI platform's audience setting must
   match the registered client id.
4. **`domain_id` given as a name**, or an agency name that exists in a
   different account than the domain id names.
5. **Token freshness/formatting** — tokens are short-lived by design; a
   trailing newline in the token file is tolerated, other whitespace is not.

## Standing rules

- **Never put long-lived keys in CI.** Where a pipeline still uses static
  keys as an interim, scope them to a protected environment with required
  reviewers, and **never pass them as command-line variables** — command
  lines land in process listings and job logs. Environment injection only.
- **Credential-free by default**: validation, plan-preview and PR jobs get no
  credentials. Only the apply job is credentialed, behind an approval gate
  (assets/plan-triage-drift).
- **Pass the security token explicitly.** The provider does not reliably pick
  the session token up from the environment; wire it through as an explicit
  variable alongside the key pair, and never echo any of the three.
- **Credentials are per-run and disposable.** A run that needs to reuse
  credentials across jobs is a design smell; mint again instead.
- Every call made by the deploy agency is audited under that principal —
  which makes "no API calls outside the deploy principal" a measurable
  acceptance criterion for a zero-console-steps claim.
- A resource-level token exchange exists as an alternative to provider-level
  auth, but it mints a much longer-lived token and lands in state. Prefer
  provider-level auth; check the provider version floor before relying on
  either.
