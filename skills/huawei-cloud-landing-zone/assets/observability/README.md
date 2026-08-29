# Observability [REUSABLE]

## Log convergence

- CTS stream + DNS query logs + CFW traffic/access/attack streams + one
  flow-log stream per VPC, all converged into the LTS delegated-admin
  account, then transferred to a KMS-encrypted archive bucket.
- **Admin-local sources transfer directly** (never converge — converging a
  local source is invalid).
- The log-target groups belong to the observability env even when their
  sources (CFW, resolver) live elsewhere — a fresh deploy is strictly one
  ordered pass, so ownership follows the env order, not the source.

## Live-API behaviors

- **`LTS.2101` on concurrent encrypted transfers**: the first encrypted
  transfer triggers LTS's async self-authorization (KMS grant to
  `op_svc_lts`); concurrent creates fail with
  `LTS.2101 "kms authorisation to op_svc_lts error"`. Serialize transfer
  waves via `depends_on`; the error is retryable — a second apply clears
  stragglers.
- The KMS service default key (`evs/default` and friends) only materializes
  on first CONSOLE use — data-source lookups against it fail on fresh
  accounts. Create explicit keys instead of depending on service defaults.
- Config/RMS org conformance packages require EVERY template parameter
  explicitly (`RMS.00010004`) and an ENABLED recorder in the creating
  account (`RMS.00010091`); parse defaults from the template BODY (the
  parameter LISTING returns lossy empty defaults the API then rejects).
- A KMS-encrypted recorder bucket needs agency KMS grants (the quick-grant
  agency omits KMS) or writes fail `RMS.00010006` / OBS 403.
