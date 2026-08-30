# Network topology: ER hub-and-spoke with centralized inspection [DOMAIN]

## Core shape

- One Enterprise Router (ER); hub VPC(s) in the shared-infra account; spoke
  VPCs per workload account, shared to the ER via RAM.
- **Three fixed route tables** encode the whole inspection topology:
  - `er-inbound` — all hub+spoke attachments associate; static 0.0.0.0/0 → CFW.
  - `er-outbound` — CFW associates; VPC CIDRs propagate; 0.0.0.0/0 → the SNAT VPC attachment.
  - `er-hybrid` — VPN/Direct Connect attachments associate; **both**
    0.0.0.0/0 → CFW **and** `<private supernet>` → CFW keep on-prem traffic
    inspected. Both routes are required: the hybrid table's routes are what
    get advertised to the on-prem peer, and a default route is frequently not
    advertised or not accepted by the peer device — the explicit supernet
    route is the one on-prem reliably learns. It is also the safety net once
    propagation is enabled on a hybrid table (a propagated per-VPC prefix
    would otherwise beat 0/0 and bypass inspection). Never remove it as a
    "duplicate of 0/0".
  Hard-code these three; do not make routing topology user-configurable.
- East-west firewall mode `er`: CFW gets its own ER attachment; traffic is
  steered through the fixed tables. The CFW *instance* lives in the network
  module; the *rule plane* is a separate module/env so rule changes never
  risk the firewall itself.
- ER **rejects static routes to VPN attachments** (`ER.04006105`; allowed
  next-hop types: vpc, peering, cfw, connect, 5G) — on-premises reachability
  exists only via gateway propagation (BGP, or static peer-subnet lists).
  There is no static fallback: cloud→DC flows exist only while the
  tunnel/BGP is up. Design reviews must flag any plan that assumes one.
- Spokes without an ER-attachment row deploy deliberately UNATTACHED
  (isolated) — treat attachment as an explicit design decision, and see
  assets/dns for the DNS hazard on unattached spokes.

## Live-API behaviors to design around

- **RAM share association is asynchronous**: a spoke attaching seconds after
  its account becomes a share principal is denied
  `common.01010013 er:instances:createVpcAttachment`. Insert a propagation
  delay (e.g. `time_sleep` ~60s keyed on the principal set).
- **RAM resource types bind one permission each and want full URNs**
  (`er:instances`, not `er:enterpriseRouter` — the wrong type errors
  `ram.1009`). `allow_external_principals` must be false or an SCP that
  denies unauthorized sharing blocks the create (`SYS.0403`).
- **Owner-side APIs**: ER route-table associations/propagations, RAM-share
  writes, and post-create attachment tag updates must run under the
  hub/owner provider — a member gets `common.01010013`. Org-sharing
  enablement is master-account-only (404 from a member agency), and
  destroying that resource is a no-op (it does not disable sharing).
- **VPN gateway public EIP blocks are create-only**: changing them
  force-replaces the gateway = new public IPs = site down until the far end
  reconfigures. Keep VPN in its own env/state (blast-radius ordering) and
  gate any plan that touches it.
- VPN gateway AZs must be selected via the per-flavor availability-zone data
  source — hard-coded AZs that don't stock the flavor fail with
  `VPN.0001: resource not enough`.
