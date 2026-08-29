# Hybrid connectivity [REUSABLE]

Huawei CAF prescribes Direct Connect / VPN / Cloud Connect per topology
(caf_01_0049). This framework automates exactly one of the three.

## What the framework wires today: site-to-site VPN

Fully spec-driven, in Terraform:

- VPN gateways (in the hub, attached to the ER — see
  assets/network-topology),
- customer gateways (peer public IP, BGP ASN if dynamic),
- VPN connections (tunnels, PSKs handed over out-of-band, never in the
  spec),
- ER **hybrid route table** association/propagation so spokes reach the
  tunnel via the hub.

Gotcha: VPN gateway AZ stock varies by region and account age — check
assets/fresh-account-preflight before planning a fresh-account VPN env.

## What it does NOT automate

- **Direct Connect**: the physical port order, carrier cross-connect, and
  commercial contract are outside Terraform entirely.
- **Cloud Connect**: the cross-region backbone instance and bandwidth
  packages involve commercial purchase steps.

For both, the framework's role is limited to:

1. **Recording the design intent** — bandwidth, locations, redundancy — in
   the spec/decisions file, and
2. **Attaching an already-provisioned DC virtual gateway or CC instance to
   the ER hybrid route table** once it exists.

## The boundary, stated honestly

If a customer requires DC or CC, say what the framework delivers (the ER
attachment and routing) and what it does not (the circuit). Do not generate
Terraform that pretends to provision a physical circuit; do not leave the
carrier lead time out of the delivery plan.
