# Billing modes: charging_mode doctrine [PLATFORM]

Pay-per-use → monthly (prePaid) conversions are placed in the BSS console;
whether Terraform notices depends on whether the resource's Read sets
`charging_mode`.

## Per-resource behavior

| Resource | Read sets it? | Schema | Effect of a console conversion |
|---|---|---|---|
| `compute_instance` | yes (server metadata) | Optional+Computed, **not** ForceNew | config must be updated to `prePaid` |
| `evs_volume` | yes, only when the disk has a BSS orderID | Optional+Computed+**ForceNew** | absorbed, leave unset |
| `vpc_eip` | yes (`Profile.OrderID`) | Optional+Computed | absorbed, leave unset |
| `natv3_gateway` | **no** (but `billing_info` is set) | Optional+Computed+ForceNew | invisible; read `billing_info` (BSS order id) to tell |
| `cbr_vault` | yes | Optional+Computed+ForceNew | absorbed, but `auto_expand` is rejected on prePaid vaults |

## Doctrine

- Leave `charging_mode` **unset** wherever possible. Optional+Computed means
  the refresh absorbs whatever BSS says — no plan diff either way. Pinning
  it on a ForceNew resource that has *not* been converted plans a
  **replace** (data loss on EVS).
- `compute_instance` is the exception that must be pinned after conversion:
  its Update only converts *to* prePaid and hard-errors
  "only support change to pre-paid" if config still says `postPaid` against
  a converted instance.
- `period_unit`/`period` are create-only and never returned by any of these
  APIs — put them in `ignore_changes` next to a pinned `charging_mode`.
- **Applying a `postPaid -> prePaid` diff makes Terraform place the BSS
  order itself. That is a purchase, not a state fix** — convert in the
  console first, then persist with `terraform apply -refresh-only`
  (state backup first; a plain `plan` saves nothing).

## Cannot be converted at all

- **Traffic-billed EIPs** (`bandwidth.charge_mode = "traffic"`) — monthly
  EIPs must be bandwidth-billed; a traffic-metered EIP stays pay-per-use.
- **Auto-expanding CBR vaults** — `auto_expand` is rejected on a prePaid
  vault, and freezing a near-full vault's size fails its backups within
  days. Converting requires giving up auto-expand: a design decision, not a
  billing toggle.
