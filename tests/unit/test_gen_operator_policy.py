"""gen_operator_policy: the scoped Terraform operator policy, bucket parameterised.

Checks the emitted document is IAM 5.0 JSON, keeps both member-account assume
statements (the tree uses the IAM 3.0 call; dropping it 403s every
cross-account env), scopes state access to the given bucket only, and stays
under the custom-policy size limit. --spec reads the same bucket from the spec.
"""

import json
import subprocess
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[2] / "pipeline"
FIXTURE = PIPELINE / "lz_pipeline/fixtures/example.spec.json"


def _run(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "lz_pipeline.tools.gen_operator_policy", *args],
                          cwd=PIPELINE, capture_output=True, text=True)


def test_policy_is_scoped_and_under_the_size_limit(tmp_path):
    out = tmp_path / "policy.json"
    r = _run("--state-bucket", "acme-lz-tfstate-01", "--out", str(out))
    assert r.returncode == 0, r.stderr
    policy = json.loads(out.read_text(encoding="utf-8"))

    assert policy["Version"] == "5.0"
    sts = {s["Sid"]: s for s in policy["Statement"]}
    assert len(sts) == 8
    assert sts["EnterMemberAccounts"]["Action"] == ["sts:agencies:assume"]
    assert sts["EnterMemberAccounts"]["Resource"] == ["iam::*:agency:OrganizationAccountAccessAgency"]
    assert sts["EnterMemberAccountsIam3"]["Action"] == ["iam:tokens:assume"]
    assert sts["EnterMemberAccountsIam3"]["Resource"] == ["iam::*:agencies:OrganizationAccountAccessAgency"]
    assert sts["StateBucket"]["Resource"] == ["obs:::bucket:acme-lz-tfstate-01"]
    assert sts["StateObjects"]["Resource"] == ["obs:::object:acme-lz-tfstate-01/*"]
    assert len(json.dumps(policy, separators=(",", ":"))) <= 6144

    from_spec = json.loads(_run("--spec", str(FIXTURE)).stdout)
    assert {s["Sid"]: s.get("Resource") for s in from_spec["Statement"]}["StateBucket"] == \
        ["obs:::bucket:example-lz-obs-tfstate-01"]
