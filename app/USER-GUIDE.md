# LZ Pipeline App — User Guide

Everything from installing the package to operating a landing zone with it.

---

## 1. Getting started

### 1.1 What you need

| Requirement | Needed for | Install (Windows) | Verify |
|---|---|---|---|
| Python 3.10 or newer | everything | `winget install Python.Python.3.12` | `py --version` |
| openpyxl (Python package) | everything (Excel generation) | `py -m pip install openpyxl` | `py -m pip show openpyxl` |
| Terraform 1.6.3 or newer on PATH | cloud jobs only (Preflight / Plan / Apply / Drift) | `winget install Hashicorp.Terraform` | `terraform version` |
| Huawei Cloud AK/SK with OBS access | cloud jobs only | issued in the Huawei Cloud console (My Credentials → Access Keys) | see section 6 |

Alternatives for Terraform: `choco install terraform` (Chocolatey), or
download the zip from https://developer.hashicorp.com/terraform/install,
unzip it, and add the folder containing `terraform.exe` to PATH.

Open a NEW terminal after installing so PATH changes take effect, then run
the Verify commands in the table.

### 1.2 Install and run

1. From the repo root: `pip install .` (gives you the `lz-app` and `lzctl` commands).
2. Run:

       lz-app

If `lz-app` or `lzctl` is "not found" after installing, your Python scripts
folder is not on PATH. Both always work as modules — no PATH change needed:

    py -m lz_app.server            # same as lz-app
    py -m lz_pipeline.lzctl        # same as lzctl  (add --version to check)

   The app starts on `http://127.0.0.1:8600` and opens your browser.

Options:

    lz-app --port 8611            # different port
    lz-app --no-browser           # don't open the browser
    lz-app --workspace <dir>      # run from anywhere; point at your workspace root

You can also set the environment variable `LZ_WORKSPACE` to the workspace root
instead of `--workspace`. The app finds its workspace automatically when run
from inside the repo.

The app binds to 127.0.0.1 only — it is a local tool, not a shared web server.

### 1.3 First five minutes

1. Copy the packaged example into your spec folder (one time):

       copy pipeline\lz_pipeline\fixtures\example.spec.json specs\lz.spec.example.json

   Then pick **`lz.spec.example.json`** in the top-right dropdown and press
   **Load**. This is a complete example: every fillable table is populated.
2. Click through the sheets in the left rail to see how a landing zone is
   described: accounts, networks, firewall rules, logging, and so on.
3. Press **Validate** — you should see "Validation passed — 0 errors, 0 warnings".
4. Open the **Build specs** job tab and press **Run** — this generates the
   Terraform inputs for every environment. No cloud access is involved.

---

## 2. Package layout — what each folder is, and what you may edit

    <workspace>\                          (the repo checkout, or your own folder)
    ├── USER-GUIDE.md                    this guide (app\USER-GUIDE.md in the repo)
    │
    ├── specs\                           ★ YOUR SPEC FILES LIVE HERE
    │   └── lz.spec.<customer>.json      specs you create with "New" are saved here
    │
    ├── pipeline\lz_spec\                CORE — do not edit
    │   ├── schema.py                    defines every sheet/column
    │   └── landing_zone_spec.xlsx       generated blank Excel template
    ├── pipeline\lz_pipeline\fixtures\  example.spec.json — filled example
    │                                    spec (copy into specs\ to explore)
    │
    ├── app\lz_app\                      CORE — the web app itself, do not edit
    ├── pipeline\lz_pipeline\            CORE — engine, runner, tools, tests, do not edit
    │
    └── terraform\
        ├── scaffold\                    blank scaffold — do not edit (template for new trees)
        ├── envs-example\                GENERATED reference tree — regenerate, don't hand-edit
        └── modules\                     Terraform module library — do not edit

Created at runtime (not in the zip):

    <envs-dir>\lzctl-logs\               ★ DETAILED LOGS of every cloud job run
    <envs-dir>\state-backups\            automatic state snapshots before each apply
    <envs-dir>\<env>\secrets.auto.tfvars.json   your credentials (never packaged/committed)
    dist\docs\                           generated documents (Export artifact job)
    dist\artifact\                       the packaged customer Terraform artifact
    drift-report.md                      report written by the Drift job

Rules of thumb:

- **Edit through the app.** The JSON spec is the single source of truth;
  everything under `envs-*` is generated from it. If you hand-edit a generated
  file, the next Build overwrites it.
- **Never edit `schema.py`, `lz_pipeline\`, `lz_app\`, `terraform\modules\`** — these
  are the product. The Schema check job will catch accidental changes.
- The Excel workbook is an **output** (Export artifact job), never an input.

---

## 3. The spec editor

The left rail starts with **Decisions & gaps** (section 3.3), then lists the 13
sheets of a landing-zone specification in build order (Global settings, then
01 Foundation through 11 SGACL, plus File Info).

### 3.1 Reading a sheet

- Every table carries a badge:
  - **MANDATORY** — free/core platform configuration; fill it in.
  - **OPTIONAL — billable** — paid service; leave empty if not needed.
  - **AUTO** — filled in automatically at build time when left empty
    (for example LogConverge); rows you add take precedence.
  - **RESERVED** — not implemented yet; input is disabled.
  - **FIXED** — platform wiring shown greyed out for information only
    (for example the three Enterprise Router route tables); no input.
- **Column guide** (above each table) expands to explain every column.
- Reference fields are **dropdowns** listing the values you defined in their
  source table — e.g. a VPC column offers the VPC names from the VPCs table.
  A red "(missing)" entry means the referenced row was renamed or deleted.
- Some fields appear only when relevant (e.g. firewall subscription fields
  only when the charging mode is "subscription").

### 3.2 Working with files

| Action | What it does |
|---|---|
| dropdown + **Load** | open a spec from `specs\` |
| **New** | create a fresh spec (give it a name like `lz.spec.customer.json`) |
| **Validate** | full structural + platform-rule check; errors link to the offending sheet |
| **Save** | write back to the loaded file |
| **Save as** | save a copy under a new name in `specs\` |

Validate before every build. Errors block the build; warnings are advisory.

### 3.3 Decisions & gaps

When a spec comes from a filled assessment questionnaire, `lzctl assess`
writes a decisions file beside it, and **the build refuses to run while any
OPEN decision is unresolved**. This view is where you clear that gate.

**Open decisions** — each one is a question nobody has answered yet. Pick a
resolution, say who decided and why, and press **Record resolution**:

| Resolution | Use it when |
|---|---|
| ANSWERED | you obtained the real answer |
| ACCEPTED_DEFAULT | the customer signed off on the proposed default |

Both *Approved by* and *Reason* are required — a resolution that doesn't record
who decided isn't auditable, and the gate rejects it. The app writes **only**
the resolution; the decision itself is fingerprinted into the spec, so editing
the question or deleting an item blocks the build exactly like leaving it open.

**Gaps** — values still sitting in the spec as `REPLACE_WITH_…` placeholders.
These are facts no questionnaire question asked for (an on-prem DNS IP, a peer
gateway's public IP, a certificate ID). Each one links to the sheet holding it;
fix it there, then Save. A placeholder left anywhere fails validation, so it can
never reach Terraform.

A fully answered questionnaire produces **zero** open decisions — that is not
by itself proof the spec is complete. The gaps list is.

---

## 4. Pipeline jobs

Set **Environments directory** once (top of the Pipeline jobs panel) — all
jobs use it. It defaults to `terraform/envs-example`. When you
build a new customer, point it at a new tree (e.g. `envs-customer`).

| Job | What it does | Cloud access |
|---|---|---|
| **Schema check** | full offline regression suite: regenerates outputs and compares, checks templates, platform rules, dependencies, formatting, runs all unit tests | none |
| **Build specs** | generates tfvars + Terraform files for every environment from the loaded spec | none |
| **Preflight** | checks Terraform version, backend credentials, checksum settings, dependency file | reads backend |
| **Plan** | `terraform plan` per selected environment in dependency order, flags risky changes, adds a cost summary | read-only |
| **Apply** | applies selected environments in order, with state backup + plan review before each | **writes** |
| **Drift** | compares live cloud state to Terraform for selected environments; marks known-harmless drift | read-only |
| **Export artifact** | regenerates documents and packages the customer deliverable | none |

Job behaviour:

- **Plan / Apply / Drift** have an environment picker — tick the environments
  to include; whatever you pick always runs in dependency order.
- **Apply defaults to dry run.** Untick "Dry run" and you get a warning box
  plus a browser confirmation before anything real happens. Destructive plans
  are additionally blocked by the triage gate.
- **Export artifact** lets you choose components: the document set
  (IP plan, configuration book, checklist) → `dist\docs`, the Excel workbook →
  `handover-docs`, and the Terraform package → `dist\artifact`.
- The console streams output live. Result chips: green **OK**, amber
  **CHANGES / DRIFT FOUND** (terraform found differences — expected, read the
  console), red **FAILED** (read the console, then the full log).
- Every cloud job writes a complete log to `<envs-dir>\lzctl-logs\` —
  the console shows the path when the job finishes.

---

## 5. Typical workflows

### 5.1 Explore the example (no cloud, no credentials)

Copy the packaged example into `specs\` (section 1.3), load it → browse sheets → Validate → Build specs →
inspect `terraform\envs-example\` → Schema check to see the whole test
suite pass.

### 5.2 Start a new customer

1. **New** → name it (e.g. `lz.spec.customer.json`).
2. Fill the sheets in order — Global, then 01 Foundation (accounts, OUs),
   05 Network (VPCs, subnets, firewall), and onward. Use the example spec as
   a reference for shapes and naming.
3. **Validate** until clean, **Save**.
4. Set Environments directory to a new folder (e.g. `envs-customer`)
   and run **Build specs**. The first build scaffolds the tree from `terraform/scaffold`.
5. `terraform init` in each environment folder (one-time, downloads the
   provider), or let Preflight tell you what's missing.
6. Add credentials (section 6), then **Preflight** until green.
7. **Plan** all environments; review.
8. **Apply** environment by environment, in order, starting with 00-bootstrap.

### 5.3 Day-2 operations

- **Change something**: edit the spec → Validate → Build → Plan (see the
  change) → Apply.
- **Suspect manual changes in the console**: run **Drift** — it reports per
  environment and writes `drift-report.md`. Known-harmless drift (documented
  quirks) is labelled as such.
- **Hand over to a customer**: **Export artifact** with all three components;
  the deliverable lands in `dist\artifact` with docs in `dist\docs`.

---

## 6. Credentials

Cloud jobs need a Huawei Cloud access key for the OBS state backend and the
provider. Two ways to supply it, both kept off the browser and out of logs:

1. **Secrets file (recommended, one-time)** — in each environment folder,
   create `secrets.auto.tfvars.json`:

       {"master_access_key": "<AK>", "master_secret_key": "<SK>"}

   The app auto-loads it for Preflight / Plan / Apply / Drift. It is
   git-ignored and never packaged.

2. **Per-job entry** — each cloud job has a "Backend credentials" panel;
   fill AK/SK there (password fields) to override for that run. Leave blank
   to use the secrets files. The request/response checksum settings default
   to `when_required`, which is what Terraform 1.11+ needs.

The app never displays, stores, or logs the key values.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `workspace not found` on startup | run from inside the package, or pass `--workspace <package root>` |
| Port already in use | `lz-app --port 8601` |
| Preflight: missing `AWS_ACCESS_KEY_ID` | no secrets file found — create one (section 6) or fill the credentials panel |
| Preflight: checksum value "must be when_required" | your shell exports conflicting `AWS_*CHECKSUM*` variables; unset them |
| Schema check: "validate: PASS (0/0 envs valid)" | no environment is `terraform init`-ed yet — expected on a fresh package; init the envs to include them |
| Plan/Apply: provider download fails | check proxy/network; `terraform init` needs registry access once per env |
| Job chip shows CHANGES / DRIFT FOUND | not an error — terraform found differences; read the console and the report |
| Build refuses: validation errors | fix the listed sheet/table entries (click the sheet link in the error card) |

For anything deeper, the full run logs are in `<envs-dir>\lzctl-logs\`.
