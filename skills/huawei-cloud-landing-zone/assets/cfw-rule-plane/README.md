# Firewall rule plane [REUSABLE]

The firewall **instance** and its **rule content** are different concerns with
different blast radii. Keep them in separate modules and separate envs: rule
changes then never risk the instance, and an instance change never orphans
the rules. Never author rules in the env that creates the firewall.

## Composition

Groups first, rules reference them: address groups (+members), domain-name
groups, service groups (+members), ACL rules, black/white lists.

- A rule takes source, destination, and service. Source accepts a
  CIDR/address-group/any; destination additionally accepts a domain group;
  service accepts an inline `protocol/srcport/dstport`, a service group, an
  L7 application, or `any`.
- **One domain group per rule** — a rule cannot reference two.
- `service = any` overrides everything else on the rule. It is also the only
  way to express protocols outside TCP/UDP/ICMP (IPsec ESP, for example), so
  scope those rules tightly by source and destination instead.
- **Address-group members must not overlap each other.** Overlapping members
  fail create with no ID in the API response. Collapse nested CIDRs before
  emitting, and validate it pre-plan — this is cheap to check and opaque to
  diagnose.
- Domain matching is **per label**: an apex domain does not match its
  subdomains. Expand to explicit wildcards. Protocols without SNI (mail, for
  one) must use a *network*-type domain group, not an application-type one —
  and note the group's own type encoding differs from the encoding the rule
  uses to reference it.

## Bind every group to the internet protect object

Groups bound to the VPC protect object work in rules but are **invisible to
the console and the list API** — operators conclude the config is missing and
recreate it. Bind all address and service groups to the internet object;
rules on either border accept them (assets/silent-failures).

Rebinding an existing group needs `create_before_destroy`: the binding is
ForceNew, and destroying the old group first fails while rules still
reference it.

## Rules are unidirectional; the border is whitelist-only

With catch-all denies in place, **every flow needs an allow in its own
direction**. Authoring only the cloud-initiated leg silently breaks:

- directory replication and any server-initiated callback,
- agent check-ins from on-premises tooling,
- return sessions on ephemeral high ports where the protocol demands them,
- both legs of a bidirectional tunnel underlay.

So: for each integration, author the pair — `<zone>-to-<peer>` and
`<peer>-to-<zone>` — with the same service groups on both. Name them so the
pairing is obvious in a rule list.

**Allows a catch-all must never be without:** DNS to the hub resolver. Every
subnet's DHCP points at it, so a VPC-border catch-all without an explicit
`any → resolver-endpoint:53` allow takes DNS down organization-wide
(assets/dns). Once internet egress exists, spoke→internet flows also cross
the VPC border and need VPC-border allows in addition to the egress rules.

## Ordering and the catch-all fail-open window

- Rules pin to the bottom in creation order. Anchoring a rule to the top
  without naming the rule it goes above is rejected outright.
- Keep catch-all denies in their **own resource** that depends on the rule
  set, so parallel creation can never land a deny above an allow.
- Re-anchor the catch-alls on the **set of rule ids**, never on the rule
  collection as a whole — the latter replaces the denies on every apply, each
  replacement a brief fail-open window on that border
  (assets/silent-failures). Expect "1 add + catch-alls replaced" as the
  normal plan shape when adding a rule, and know the border is briefly open
  during it.
- Prefer disabling a rule over deleting one that will come back. Break-glass
  is disabling a catch-all — which opens that entire border to everything not
  explicitly denied. Say that out loud when proposing it.

## Firewall rules and security groups are not the same layer

| Layer | Sees | Carries |
|---|---|---|
| Firewall | between VPCs, to/from VPN, to/from internet | the precise source lists |
| Security group | the instance NIC, **including intra-VPC traffic the firewall never sees** | coarse port-level rules |

Keep security-group sources coarse (supernets, tier references) and let the
firewall hold exact CIDRs. Two planes maintaining the same IP list drift
apart. Where default rules are deleted on creation, the group's rule list is
the entire policy — every group needs an explicit egress row.

**"Firewall allows, security group blocks" has no automated cross-check.**
The planes live in different envs and states. Audit it deliberately: read the
firewall access logs to find which rule denied a flow, then confirm the
matching NIC-level rule exists. Treat a new firewall allow as incomplete
until its security-group counterpart is checked.

## Plan economics

Every group *member* is its own resource, so a mature rule plane runs to
hundreds of resources in one state, and a plan re-reads all of them — tens of
minutes. For a small edit, **rebuild and review the diff; do not self-verify
with a full plan.** Budget the verification plan for the apply gate
(assets/apply-orchestration).

## Billing: flipping the mode replaces the firewall

On the firewall instance, `charging_mode`, the period fields, and `flavor`
are all ForceNew. Changing billing in config therefore **destroys and
recreates the firewall** — new protect-object IDs, the entire rule plane
recreated or orphaned, and a fresh order placed while the old subscription
still runs. That is the double-charge shape.

Convert billing in the console, then reconcile state with a refresh-only
apply (assets/billing). Flavor naming is case-sensitive and rejects lowercase
with an unrelated-sounding third-party-interface error; some flavors exist
only under one billing mode.

## Alarms and logs

- Alarm categories (attack, traffic threshold, unprotected address, threat
  intelligence) are individually toggleable and **default off**. Each resolves
  a notification topic **by name** in the firewall's account, so the
  observability env that creates the topics must apply first — assert this
  with a postcondition that names the fix, not a null reference.
- The alarm type is immutable; severity, frequency, and topic are updatable.
- Firewall logs (access, attack, flow) converge through the log service like
  any other stream (assets/observability). A one-click monitoring bundle for
  the firewall namespace is a separate, independent channel from these alarms.

## North-south rules are dormant until addresses are protected

Internet-border rules do nothing until the public addresses are actually
placed under firewall protection. A clean apply is not evidence that internet
egress is being inspected — verify protection status separately.
