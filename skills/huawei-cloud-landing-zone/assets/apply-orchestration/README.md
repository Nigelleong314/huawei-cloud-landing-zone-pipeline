# Apply orchestration [RUNBOOK]

- Order = numeric env order, derived from `deps.json` — never hardcoded in
  CI. Later envs read earlier outputs via `terraform_remote_state`.
- Wrap Terraform in a runner that provides: preflight (versions,
  credentials, checksum vars, deps freshness), advisory lock, state backup,
  saved-plan apply (`-out tf.plan`, apply that saved plan file), plan triage gate,
  retry-once on known transients (LTS.2101, EPS grant propagation,
  fresh-agency 403).
- Plan triage exit convention: 0 clean · 2 changes (reviewable) ·
  3 destructive (blocked without explicit approval).
- Plan wall-clock scales with estate size — a plan re-reads every managed
  resource, so a several-hundred-resource env (e.g. the firewall rule plane)
  alone can take tens of minutes. For a small text edit in such an env,
  prefer edit + rebuild + review over self-verifying with a full plan;
  budget the verification plan for the apply gate.

## Removing an account's last spoke

Deleting the account's last spoke row also deletes that account's generated
provider alias, but the state still holds resources → plan fails with
"Provider configuration not present". Drop a temporary hand-written provider
block with the same alias (e.g. `providers-decommission.tf`), run the
destroy, delete the file. Generators never touch non-generated files, so it
persists until removed.
