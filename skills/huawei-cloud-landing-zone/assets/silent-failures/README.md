# Silent-failure traps [REUSABLE]

Configurations that produce **no error** — the plan is clean, the apply
succeeds — while doing the wrong thing. These are the highest-value checks
in any review because nothing else will catch them.

## 1. Enterprise-project-scoped data sources returning empty

List APIs default to the DEFAULT enterprise project ("0") when
`enterprise_project_id` is omitted. A resource that lives in a NON-default
EP then returns an **empty list** → `for_each` over nothing → zero resources
created → the feature toggle reads true while nothing is enforced.

- Symptom shape: a sibling feature scoped by object id works, the EP-scoped
  one silently doesn't.
- Fix: pass `enterprise_project_id` to the **data source** that enumerates.
  Do NOT add it to resources where it is NonUpdatable — pre-existing
  resources with it empty then fail every re-apply with
  "<field> can't be updated".

## 2. `replace_triggered_by` on a whole resource

Referencing a whole resource fires on **any planned update** of it — a
lifecycle edit on a bucket destroys/recreates its public-access-block, with
a real unprotected window between DELETE and PUT; a map-keyed trigger
replaced firewall catch-all denies on every apply (brief fail-open windows).

- Prefer triggering on a specific **attribute**, or key a `terraform_data`
  resource on the exact id-set whose change should re-anchor.
- Ask of every `replace_triggered_by`: "what is live-degraded during the
  destroy→create window, and what makes it fire?"

## 3. NonUpdatable fields and `enable_force_new`

Some resources mark every argument NonUpdatable and the provider's default
(`FlexibleForceNew`) is to **fail the plan** on change, not replace
("<field> can't be updated"). The per-resource escape hatch is the
undocumented string attribute `enable_force_new = "true"`, which flips the
diff to ForceNew.

- Safe only when the resource is action-style (Delete makes no API call) —
  a "replace" is then state-removal + one POST that overwrites server-side
  settings, and nothing is ever unset live. Verify Delete's behavior in the
  provider Go source before using it.
- Prefer the per-resource attribute over the provider-level bool (which
  would apply to every resource in that provider config).

## 4. Unattached-spoke DNS black-hole

See assets/dns — subnet DHCP pointed at a hub resolver that is unreachable
without an ER attachment kills all DNS in the VPC, and Optional+Computed
DNS attributes mean Terraform never repairs an already-deployed subnet.

## 5. Console-invisible resources

Some scoping choices work functionally but are invisible to console/list
APIs (e.g. firewall address groups bound to the VPC protect object work in
rules but never appear in the console). Operators conclude the config is
missing and recreate it. Bind to the scope the console displays.

## Reviewing for silent failures

For any `for_each` over a data source: ask "what does an EMPTY result mean
here, and would anyone notice?" — gate on `length > 0` or emit a check
block/precondition when empty means misconfiguration rather than "none
needed".
