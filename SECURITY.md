# Security

## Reporting a vulnerability

Open a GitHub issue marked `security`, or contact the maintainers directly (contact: see the repository owner profile — placeholder until a security mailbox is published). Please do not include exploit details in a public issue; say enough to be contacted.

## Credentials

- **No credentials in the repo or the spec — ever.** The spec schema states it (`Global`: "AK/SK never live here"), and the pipeline enforces the pattern: Huawei AK/SK come from the `HW_ACCESS_KEY` / `HW_SECRET_KEY` environment variables and are written only to each env's `secrets.auto.tfvars.json`, which is gitignored and excluded from exports (the export test asserts no such file ships).
- Backend credentials are environment variables too (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for the OBS S3-compatible endpoint).
- The verify harness strips `HW_ACCESS_KEY` / `HW_SECRET_KEY` from the environment before rebuilding, so verification can never (re)write secrets.

## The destructive-apply double-gate

A plan containing destroys exits with code 3 and **blocks** apply. Proceeding requires `--allow-destroy` *and* a second, typed confirmation of the exact env name — `--yes` never bypasses it. CI pre-authorizes a single named env with `--destroy-confirm <env>`, nothing broader. There is no flag combination that destroys silently.

## State files

Terraform state is never committed. It lives in the OBS backend; local copies exist only as deliberate backups under `state-backups/` (created before every apply) inside customer workspaces, which are not part of this repo. Treat any state file as sensitive: it contains resource IDs and can contain secret material.

## Evidence bundles

`lzctl report` bundles logs, the dependency graph, a drift report, and version info. Bundles may contain resource IDs, account names, and infrastructure detail — **review a bundle before sharing it outside the engagement**, and prefer sharing the `MANIFEST.txt` hashes when a recipient only needs integrity proof.

## What ships to customers

Exported artifacts are scanned by the leak-guard test for customer-derived identifiers (including on-prem CIDR prefixes and domains) so one customer's data cannot leak into another's artifact or into the public examples.
