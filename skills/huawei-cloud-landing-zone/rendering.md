# Rendering goldens

Companion to SKILL.md "Rendering". The four rules (verdict first ·
exceptions only · one Next · words only), the strip, and the default phase
report live there; this file carries the exact templates for everything
else. Copy the shape, fill the slots, omit empty sections. These are exact
templates — do not restyle, reorder, or decorate them.

Shared skeleton for every verb card: `### VERB — subject · verdict (exit n)`,
then exception bullets or a per-env grid, then **Next** as one fenced bash
block, then the provenance line (`runner · cloud: x · undo: y`) or the
artifact paths when the record is a file.

## Phase report — full form (explicit ask only: "full status", `-v`)

**FRASERS** — 4/7 complete · 13 envs
`spec` lz_spec/lz.spec.frasers.json · `envs` huawei-lz/envs-frasers

| Phase | Status |
|---|---|
| 01-intake | complete |
| 02-design | complete |
| **03-build** | **recheck** — next |
| 04-verify_pre | recheck |
| 05-deploy | complete |
| 06-verify_post | complete |
| 07-deliver | pending |

*re-entered design 2026-09-01 (tester): supernet moved*

### 03-BUILD — generate the env tree

- **the spec is newer than 9 of 13 envs** — timestamp hint only; `lzctl check regen-diff` proves it
- `terraform.tfvars.json` present in all 13 envs
- `deps.json` present

**Next**
```bash
lzctl check regen-diff --envs-dir huawei-lz/envs-frasers --spec lz_spec/lz.spec.frasers.json
lzctl build ...   # only if regen-diff reports differences
```
agent · cloud: none · undo: regenerate or delete the tree

Slots: the table is always all seven rows, numbered per the phase-numbering
rule (bold current row, `— next` marker). One card per live phase — the current one plus anything `recheck`
or `blocked`. Blockers lead each card as bold-led bullets in the gate's own
words; artifacts follow as plain bullets; `needs` becomes a **Needs from
you** line; the journal line renders while a re-entry's invalidated phases
are incomplete.

## PLAN

### PLAN — frasers · 3 envs · changes present (exit 2)

| Env | Verdict | Changes |
|---|---|---|
| 05-network | changes | 2 update |
| 07-security | no changes | — |
| 09-network-cfw | **destructive** | 1 destroy, 1 create |

- **09-network-cfw** — `huaweicloud_cfw_protection_rule.block_x` will be replaced (rule reordering). Apply is blocked without `--allow-destroy`.
- cost: ~$412/mo estimated (rate card ap-southeast-3)

**Next**
```bash
lzctl apply --envs-dir huawei-lz/envs-frasers 05-network   # human at a terminal, never the agent
```
human · cloud: write · undo: none once applied — triage before every apply

Slots: grid rows in apply order, one per planned env; verdict words are the
CLI's (`no changes` / `changes` / `destructive`, destructive bold). A
destructive row always gets a bullet naming the resource and the reason —
never just the count. The cost line always names the rate card's region;
omitted when no card was given. The header verdict is the worst across
envs, with the run's exit code.

## APPLY — reporting a human's run, from lzctl-logs/

### APPLY — frasers · 05-network · applied (exit 0)

- state backup: `state-backups/20260901-101500-05-network.tfstate.json`
- plan: reused from the triage run (configuration unchanged)
- result: 2 changed, 0 destroyed
- log: `lzctl-logs/20260901-101500-apply.log`

**Next**
```bash
lzctl verify --envs-dir huawei-lz/envs-frasers
```
agent · cloud: read-only · undo: plans write nothing

Slots: one bullet set per env applied, in apply order; a failed env quotes
the CLI's FAIL line verbatim and ends the list ("earlier envs were
applied"). The state-backup path always renders — it is the undo story.
This skill never runs the apply; this card reads the record a human made.

## VERIFY / DRIFT

### VERIFY — frasers · 13 envs · fail (exit 2)

- **09-network-cfw** — DRIFT: 1 destructive, 0 update, 2 create
- 11-sgacl — known-benign drift only (3)
- 11 of 13 clean

The deployed infrastructure is inconsistent — investigate before further
changes.

**Next**
```bash
lzctl drift --envs-dir huawei-lz/envs-frasers 09-network-cfw --report drift-09.md
```
agent · cloud: read-only · undo: plans write nothing

Slots: only non-clean envs are listed; destructive drift is bold and always
first. Pass form: `### VERIFY — frasers · 13 envs · pass (exit 0)`, one
line `13 of 13 clean or known-benign`, Next = the deliver commands. A
standalone `lzctl drift` renders the same shape titled `### DRIFT —`.

## VALIDATE

### VALIDATE — lz.spec.frasers.json · 3 errors · 2 warnings (exit 1)

- 05_Network.SpokeVPCs[prod-app]: cidr 10.0.0.0/20 overlaps hub 10.0.0.0/16
- 03_Identity.AccountAssignments[3]: group "platform-ops" not defined in Groups
- 10_VPN.Connections[hq]: psk is the placeholder REPLACE_WITH_STRONG_PSK (LZR-032)

warnings: LZR-014, LZR-021 (advisory — one line, never blocking)

**Next**
```bash
lz-app --workspace .   # fix in the sheets, Validate, Save — then re-read the spec from disk
```
human · cloud: none · undo: spec edits are a git diff

Slots: every error verbatim, capped at 20 with "and n more" (the full list
stays in the command output). Errors are never summarized away — they are
the actionable content. Pass form:
`### VALIDATE — lz.spec.frasers.json · 0 errors · 2 warnings (exit 0)`.

## DECISIONS

### DECISIONS — frasers · 2 open · build blocked (exit 3)

- **C16** (open) — prod supernet CIDR, pending the IP workshop — resolve in the app, Decisions & gaps
- **G1** (open) — VPN PSK placeholder in 10_VPN.Connections — the app deep-links to the sheet
- 5 defaulted for review · 31 answered

**Next**
```bash
lz-app --workspace .   # Decisions & gaps, top of the rail
```
human · cloud: none · undo: resolutions are additive; the decision set is immutable

Slots: every open item renders — ref, the question, the venue; defaulted and
answered compress to the count line. Nothing open:
`### DECISIONS — frasers · none open (exit 0)` plus the count line.

## DOCS / EXPORT

### DOCS — frasers · 4 documents (exit 0)

- `dist/docs/`: ip-management.xlsx · config-book.xlsx · resource-checklist.xlsx · LLD workbook

**Next**
```bash
lzctl report --envs-dir huawei-lz/envs-frasers   # evidence bundle; export follows verify
```
agent · cloud: none · undo: regenerate — documents are derived artifacts

Slots: artifact names on one bullet with the output dir; a generation
failure quotes the CLI's FAIL line and drops the artifact from the list.
