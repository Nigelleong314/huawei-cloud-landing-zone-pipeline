# RGC and this pipeline

Huawei Cloud ships a native landing-zone service: **Resource Governance Center (RGC)**. This page states what RGC gives you, when it is enough on its own, what this pipeline adds, and how the two coexist.

## What RGC provides natively

Per the [RGC service overview](https://support.huaweicloud.com/intl/en-us/productdesc-rgc/rgc_01_0002.html) and [user manual](https://support.huaweicloud.com/intl/en-us/usermanual-rgc/rgc_01_0065.html):

- A **baseline landing zone** set up in roughly 30 minutes: a management account plus dedicated audit and log-archive accounts, organized into OUs.
- **Predefined governance controls** (SCP-based preventive policies plus detective controls) applied per OU.
- An **account factory** for provisioning new member accounts into the governed structure.
- **Drift detection** against the RGC-managed baseline.
- The **Landing Zone Governance Check**: a conformance scan of your landing zone against Huawei's Cloud Adoption Framework maturity models — the Standard model covers 5 governance domains, the Flagship model 8 (see also the [CAF user manual](https://support.huaweicloud.com/intl/en-us/usermanual-caf/caf_01_0001.html)).

## When RGC alone is enough

If your needs stop at a governed multi-account skeleton — management/audit/log-archive accounts, OU structure, predefined guardrails, and an account factory — and you accept console-driven, service-managed configuration as your source of truth, use RGC and stop there. It is faster to stand up and Huawei maintains the baseline.

## What this pipeline adds

- **Full 9-domain coverage**, including the domains a baseline LZ does not build: the Enterprise Router hub-and-spoke network, Cloud Firewall rule plane, enterprise-project cost structure (EPS), DNS zones and hybrid resolver, site-to-cloud VPN, and workload security groups.
- **Spec determinism**: one reviewed JSON spec is the authoritative store; regeneration is byte-identical (enforced by the `regen-diff` harness check), so config review, diffing, and audit work like code review.
- **Handover-grade plain HCL**: the customer receives readable Terraform plus a standalone runner and can operate the landing zone with no pipeline, no console archaeology, and no vendor tooling.
- **Evidence bundles**: `lzctl report` produces a hashed bundle (logs, dependency graph, drift report, tool versions) suitable for audit handover.

## Coexistence guidance

RGC managing the org baseline (accounts, OUs, baseline SCPs, account factory) while this pipeline delivers the rest (network, CFW, DNS, VPN, observability wiring, workload SGs) is a workable split. The one hard rule: **overlapping controllers for the same resources must be avoided — pick exactly one owner per domain.** If RGC owns SCPs, do not also manage SCPs from `04-perimeter`; if the pipeline owns the org tree, do not enroll it in RGC's baseline. Two controllers reconciling the same resource produce permanent drift on both sides, and each will "correct" the other.

Record the split per engagement in the spec's decisions file so the ownership boundary survives handover.

## The governance check as a post-deploy step

The Landing Zone Governance Check is a documented **manual** step after `lzctl verify` passes:

1. In the console, run the [Landing Zone Governance Check](https://support.huaweicloud.com/intl/en-us/usermanual-rgc/rgc_01_0065.html) against the deployed landing zone (choose the Standard or Flagship model per the engagement).
2. Download the conformance report.
3. Place it in the `lzctl report` evidence bundle directory (`<envs>/evidence/<ts>/`) so it ships with the rest of the delivery evidence.

The pipeline does not automate this: the check is console-driven and its report is Huawei's own attestation, which is precisely why it belongs in the evidence bundle unmodified.
