# Security policy

## Reporting a vulnerability

Report vulnerabilities privately through **GitHub Security Advisories** on
this repository (Security tab → "Report a vulnerability"). Do not open a
public issue for anything exploitable. Reports are acknowledged within a
reasonable time; coordinated disclosure is preferred.

## What this project does and does not hold

- **No credentials, ever, in the repo or the spec.** Cloud credentials enter
  only at deploy time, via environment variables or each environment's
  `secrets.auto.tfvars.json` (gitignored, never generated unless the
  variables are present, never printed).
- **State files are never committed.** The state backend is remote (OBS);
  local state artifacts, plan files, and state backups are gitignored.
- **Destructive applies are double-gated.** A plan classified destructive is
  blocked without `--allow-destroy`, and even then requires a typed env-name
  confirmation that `--yes` never bypasses (`--destroy-confirm ENV`
  pre-authorizes a specific env for CI).
- **Evidence bundles may contain resource identifiers** (IDs, IPs, names
  from your own estate). Review a bundle before sharing it outside the team
  that operates the estate.

## Scope notes for reporters

The web app binds to 127.0.0.1 with no authentication by design — it is a
local operator tool, not a service. Reports about exposing it beyond
localhost are configuration issues, not vulnerabilities, unless the default
itself is bypassed.
