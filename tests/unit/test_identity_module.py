"""Run the identity module's `terraform test` suite from pytest.

The suite (tests/terraform/identity) mocks the Huawei provider, so it never
contacts the cloud. It covers two defects found in the 2026-09-30 handover
audit - password inputs the resource never read, and a provisioning map that
failed with "Duplicate object key" when two groups shared a permission set in
one account - and pins the defaults the live estates run on.

`terraform init` still needs the provider binary for its schema. Where the
registry is unreachable, point TF_CLI_CONFIG_FILE at a filesystem mirror.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[1] / "terraform" / "identity"


def _tf(*args):
    return subprocess.run(["terraform", *args, "-no-color"], cwd=SUITE,
                          capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform not installed")
def test_identity_module_terraform_suite():
    init = _tf("init", "-input=false")
    if init.returncode != 0:
        last = init.stderr.strip().splitlines()[-1] if init.stderr.strip() else "no output"
        pytest.skip("provider not installable here (no registry or mirror): " + last)
    result = _tf("test")
    assert result.returncode == 0, result.stdout + result.stderr
