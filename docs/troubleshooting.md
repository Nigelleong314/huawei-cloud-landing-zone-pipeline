# Troubleshooting

The classics, with exact signatures where they have them. `lzctl preflight` catches the first two classes before they cost you an apply.

## `XAmzContentSHA256Mismatch` on init or state push

Terraform 1.11+ against the OBS S3-compatible backend needs both checksum variables:

```bash
export AWS_REQUEST_CHECKSUM_CALCULATION=when_required
export AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
```

Without them, state save fails **after** a successful apply — the worst moment. `lzctl preflight` verifies both.

## `terraform init` fails silently against the OBS backend

The backend block needs **all five** skip flags:

```hcl
skip_requesting_account_id  = true
skip_s3_checksum            = true
skip_region_validation      = true
skip_credentials_validation = true
skip_metadata_api_check     = true
```

Missing any of them makes `init` fail without a useful error. The scaffold's `backend.tf` files already carry all five; this bites hand-written or trimmed backends.

## `STS5.1001` when enabling Config (RMS)

The Config resource recorder needs its service agency authorized once via the console before Terraform can manage it. Grant the agency in the console, then re-run the apply for that env.

## `VPN.0001` / "resource not enough" creating a VPN gateway

The chosen availability zone is out of gateway stock — capacity, not quota. Pick a different AZ in the spec's VPN table and rebuild/re-plan. See the skill asset `fresh-account-preflight` for the capacity-vs-quota distinction.

## `EPS.0004` during apply

The enterprise-project authority grant is asynchronous; the first API call after granting can race it. This signature is in the default `LZ_TRANSIENT_SIGNATURES`, so `lzctl apply` retries once automatically (re-plan + apply of the remainder). If it fails twice, the grant genuinely hasn't landed — check EPS in the console.

(`LTS.2101`, a log-service hiccup, is the other default retry-once signature.)

## Empty KMS (or similar) data-source lookups in a fresh account

Brand-new accounts have no default keys or service-initialized resources yet, so name-based data lookups return nothing and the plan errors. Apply the envs strictly in `deps.json` order — earlier envs create what later lookups find — and see the `fresh-account-preflight` skill asset for the full list of things that don't exist yet in a fresh account.

## `FAIL <env>: the saved plan is stale` on apply

The state changed after the plan file was written (typically after a partial apply or a concurrent change). This is Terraform protecting approve-what-you-apply. Fix:

```bash
lzctl plan  --envs-dir <envs> <env>   # re-plan, review the new output
lzctl apply --envs-dir <envs> <env>
```

## The app can't find its workspace

`lz-app` locates the workspace via `--workspace`, then the `LZ_WORKSPACE` env var, then a walk-up from the current directory. Run it from inside the package, or point it explicitly:

```bash
lz-app --workspace <package-root>
```

## `terraform not on PATH`

- `lzctl preflight` fails on it (correct: plan/apply need it).
- The verify harness does **not** fail on it: the `fmt` and `validate` checks print `SKIPPED (terraform not on PATH)` and pass, so spec-only work stays testable on machines without Terraform. Install Terraform ≥ 1.6.3 to make those checks meaningful.

## Lock held: `lock held by user@host pid N`

One apply at a time per tree. If that run is genuinely dead, delete `<envs>/.lzctl.lock`; locks older than 2 hours are broken automatically with a note. Across machines, CI concurrency groups are the real serializer — the local lock is advisory.
