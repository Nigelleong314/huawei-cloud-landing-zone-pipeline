# Edge security: WAF and Anti-DDoS [PLATFORM]

## WAF (dedicated mode)

- Instance lives in the **hub DMZ** subnet; dedicated mode is the only mode
  that fits the hub-inspection topology (assets/network-topology).
- Deploy = instance + policy + domain binding; the protected domain routes
  through the WAF instance.
- **Sizing is by spec code**: engine CPU/memory are fixed per specification
  code — platform-set, not tunable fields. Pick the code, don't invent
  resource dimensions.
- The WAF instance gets its own security group. Its `0.0.0.0/0` inbound
  exposure is **deliberate and inspected** — it is the inspection point, not
  a finding. Flag it as intentional in plan triage
  (assets/plan-triage-drift), don't "fix" it.

## Anti-DDoS

- **Per-EIP basic protection**; enable on every internet-facing EIP.
- The traffic-cleaning **threshold is a platform enum** — pick from the
  published list, never a free-form number.

## Alarm wiring and apply order

Both WAF and Anti-DDoS bind alarm notifications to **SMN topics from the
observability env** — same cross-env pattern as the firewall
(assets/cfw-rule-plane): observability applies first, edge security reads
its topic outputs via remote state. Deploying edge security before
observability leaves alarms silently unbound.

## SecMaster — PENDING

**This asset intentionally records no SecMaster deployment doctrine.** The
best-practice implementation pattern for SecMaster in a landing zone is
still being sourced; nothing here is validated.

Until this section is replaced:

- Agents must **not invent SecMaster architecture** (workspaces, playbooks,
  data collection pipelines, instance sizing).
- Treat any SecMaster requirement as an **open decisions-file item** and
  say so to the requester.

This pending marker is a deliberate honesty gate — leave it in place until
real doctrine replaces it.
