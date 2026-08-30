# Provider block and authentication [PLATFORM]

Every auth method the provider supports, and which one to use where. The
provider docs' `index.md` is the source of truth for argument names — check
it before inventing one.

## The six methods, in the provider's own precedence order

| # | Method | Shape | Use it for |
|---|---|---|---|
| 1 | **Static credentials** | `access_key` + `secret_key` in the block (+ `security_token` for temporary keys) | never in committed code |
| 2 | **Environment variables** | `HW_ACCESS_KEY`, `HW_SECRET_KEY`, `HW_SECURITY_TOKEN`, `HW_REGION_NAME`; provider block can be empty | local dev, bootstrap |
| 3 | **Shared config file** | `shared_config_file` + `profile` (or `HW_SHARED_CONFIG_FILE` / `HW_PROFILE`) | engineers with several tenants |
| 4 | **Instance metadata** | nothing but `region`; credentials leased from the metadata API | Terraform running on an in-tenant VM with an agency |
| 5 | **Assume role** | `assume_role { agency_name, domain_name }`; repeat the block to **chain** roles | cross-account fan-out |
| 6 | **Assume role with OIDC** | `assume_role_with_oidc { agency_name, domain_id, idp_id, id_token_file, duration }` | CI (assets/ci-credentials-oidc) |

```hcl
# cross-account target: temp member AK/SK via an agency
provider "huaweicloud" {
  alias  = "member"
  region = var.region

  assume_role {
    agency_name = "OrganizationAccountAccessAgency"
    domain_name = var.member_domain_name   # NOT role_arn
  }

  default_tags = var.mandatory_tags        # see below
}
```

## Rules that matter more than the syntax

1. **Never hard-code credentials in HCL.** The provider docs warn about it
   because the file gets committed. Environment injection or a federated
   method only — and never as command-line `-var` arguments, which land in
   process listings and CI logs.
2. **Cross-account is `agency_name` + `domain_name`, never `role_arn`.**
   Two distinct modes exist (provider-level agency attributes vs. an
   `assume_role` block) and they are not interchangeable — picking the wrong
   one silently creates buckets in the wrong account. The selection rule is
   in assets/cross-account; read it before writing a cross-account provider.
3. **`default_tags` is mandatory on cross-account providers** where a
   mandatory-tag guardrail is enforced, or creates are denied
   (assets/cross-account, assets/scp-guardrails).
4. **Pass `security_token` explicitly** with temporary credentials. The
   documented environment fallback is not reliable in the field; wire it
   through as an explicit argument alongside the key pair.
5. **On the OIDC path, set `duration` explicitly** — the provider's long
   default duration does not apply there (assets/ci-credentials-oidc).
6. **Authenticating the provider does not authenticate the backend.** The
   S3-compatible state backend takes its own credentials and its own
   environment variables, and needs all five `skip_*` flags — a provider that
   authenticates fine will still fail `init` (assets/state-backend).
7. **Terraform cannot `for_each` providers.** One alias per target account,
   generated rather than hand-maintained (assets/repo-codegen).
8. **Role chaining is ordered**: multiple `assume_role` blocks are applied in
   sequence. Useful for a hub-then-member hop; keep chains short — each hop
   is another trust relationship to audit.

## Provider arguments worth knowing beyond credentials

- `region` — required with static credentials; otherwise sourced from the
  environment. Regional service behavior differs; `regional` forces regional
  endpoints for services that also have a global one.
- `enterprise_project_id` — a provider-level default. Setting it at provider
  level does **not** fix data sources that need it passed explicitly, and
  adding it to resources where it is non-updatable breaks re-apply
  (assets/silent-failures).
- `endpoints` — per-service endpoint overrides; needed for non-standard or
  isolated deployments.
- `max_retries` — raise it where async grants and propagation delays are
  expected (assets/fresh-account-preflight), but do not use it to paper over
  a wrong permission.
- `default_tags` / `ignore_tags` — the tagging contract; `ignore_tags` keeps
  provider-managed tags from fighting a platform that adds its own.
- `insecure`, `auth_url`, `cloud`, `signing_algorithm` — only for
  non-standard or on-premises endpoints. If a reviewer sees `insecure` in a
  landing-zone provider block, that is a finding.

## Choosing, in one line each

- **Engineer laptop** → environment variables, or a shared config profile.
- **CI/CD** → OIDC federation; temporary env-injected keys only as an interim.
- **Automation running inside the tenant** → instance metadata with an agency.
- **Any member account** → base credentials plus an `assume_role` block.
- **Anything committed** → no credentials at all.
