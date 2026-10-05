"""Generate the least-privilege IAM 5.0 policy for day-to-day Terraform runs.

The policy is assigned in the management account only: it covers the
organization-level reads and changes a plan/apply makes there, entering member
accounts through OrganizationAccountAccessAgency, and reading/writing the
state bucket. See docs/operator-policy.md for what it deliberately excludes.

Usage:
    py -m lz_pipeline.tools.gen_operator_policy --state-bucket <name> [--out policy.json]
    py -m lz_pipeline.tools.gen_operator_policy --spec lz.spec.json [--out policy.json]

Without --out the policy is printed to stdout.
"""

import argparse
import json
import re
import sys
from pathlib import Path

AGENCY = "OrganizationAccountAccessAgency"
# IAM 5.0 custom identity policy size limit (compact JSON, characters).
MAX_POLICY_CHARS = 6144
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def _reads(svc, verbs):
    return [f"{svc}:*:{v}*" for v in verbs]


def build_policy(bucket: str) -> dict:
    return {"Version": "5.0", "Statement": [
        {"Sid": "ReadForPlan", "Effect": "Allow", "Action":
            _reads("organizations", ["get", "list", "count"])
            + _reads("IdentityCenter", ["get", "list", "describe", "count", "is"])
            + _reads("eps", ["list"]) + _reads("tms", ["list", "show"])
            + _reads("ram", ["get", "list", "search"])
            + ["iam:securityPolicies:get*", "iam:projects:list*", "iam:roles:list"]},
        {"Sid": "OrganizationsChange", "Effect": "Allow", "Action": ["organizations:" + a for a in [
            "accounts:update", "accounts:move", "ous:create", "ous:update",
            "policies:create", "policies:update", "policies:attach", "policies:enable",
            "delegatedAdministrators:register", "trustedServices:enable",
            "resources:tag", "resources:untag"]]},
        {"Sid": "PermissionSetsChange", "Effect": "Allow", "Action": ["IdentityCenter:" + a for a in [
            "permissionSet:create", "permissionSet:update", "permissionSet:provision",
            "permissionSet:attachCustomPolicy", "permissionSet:detachCustomPolicy",
            "permissionSet:attachManagedPolicy", "permissionSet:detachManagedPolicy",
            "resources:tag", "resources:untag"]]},
        {"Sid": "EnterpriseProjectsAndTags", "Effect": "Allow", "Action": [
            "eps:enterpriseProjects:create", "eps:enterpriseProjects:update",
            "eps:enterpriseProjects:enable",
            "tms:predefineTags:create", "tms:predefineTags:update"]},
        {"Sid": "EnterMemberAccounts", "Effect": "Allow", "Action": ["sts:agencies:assume"],
         "Resource": [f"iam::*:agency:{AGENCY}"]},
        # Note: the provider's cross-account modes use the IAM 3.0 assume call.
        {"Sid": "EnterMemberAccountsIam3", "Effect": "Allow", "Action": ["iam:tokens:assume"],
         "Resource": [f"iam::*:agencies:{AGENCY}"]},
        {"Sid": "StateBucket", "Effect": "Allow",
         "Action": ["obs:bucket:listBucket", "obs:bucket:headBucket"],
         "Resource": [f"obs:::bucket:{bucket}"]},
        {"Sid": "StateObjects", "Effect": "Allow",
         "Action": ["obs:object:getObject", "obs:object:putObject"],
         "Resource": [f"obs:::object:{bucket}/*"]},
    ]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--state-bucket", help="OBS bucket holding Terraform state")
    src.add_argument("--spec", help="JSON spec; reads Global.Settings.state_bucket_name")
    ap.add_argument("--out", help="write the policy here (default: stdout)")
    args = ap.parse_args()

    bucket = args.state_bucket
    if args.spec:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        bucket = (spec.get("sheets", {}).get("Global", {}).get("Settings") or {}).get("state_bucket_name")
        if not bucket:
            ap.error(f"{args.spec}: Global.Settings.state_bucket_name is not set")
    if not BUCKET_RE.match(bucket):
        ap.error(f"not a valid OBS bucket name: {bucket!r}")

    policy = build_policy(bucket)
    size = len(json.dumps(policy, separators=(",", ":")))
    if size > MAX_POLICY_CHARS:
        print(f"policy is {size} chars, over the {MAX_POLICY_CHARS}-char limit", file=sys.stderr)
        return 1
    text = json.dumps(policy, indent=2) + "\n"
    if not args.out:
        sys.stdout.write(text)
        return 0
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"written: {args.out} (statements {len(policy['Statement'])}, "
          f"actions {sum(len(s['Action']) for s in policy['Statement'])}, "
          f"compact size {size}/{MAX_POLICY_CHARS} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
