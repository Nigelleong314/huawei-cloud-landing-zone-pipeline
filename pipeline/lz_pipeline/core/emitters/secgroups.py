"""11-network-sgacl: per-account workload security-group fan-out."""
from pathlib import Path

from ..helpers import MODULE_SOURCE_ROOT, _acct_alias
from ..writer import write_generated
from .common import _spoke_provider_block


_SGACL_MODULE_SRC = MODULE_SOURCE_ROOT + "/secgroups"


def _emit_sgacl_codegen(env_dir: Path, spec: dict):
    """One assume_role provider + one secgroups module call per distinct
    SecurityGroups.Account (row order). The account's whole groups/rules slice
    travels as var.secgroups["<account>"]; rules were bucketed to their group's
    account by build_09_sgacl."""
    m = spec.get("11_SGACL", {})
    accounts = [a for a in dict.fromkeys(str(r.get("Account") or "").strip()
                                         for r in m.get("SecurityGroups") or []) if a]

    prov = [
        "# --- Security group account providers ---",
        "",
    ]
    calls = [
        "# --- Security groups by account ---",
        "",
    ]
    if not accounts:
        prov.append("# Note: No account defines workload security groups.")
        calls.append("# Note: No account defines workload security groups.")
    for a in accounts:
        al = _acct_alias(a)
        prov += _spoke_provider_block(al, a)
        calls += [
            f"# Account: {a}",
            f'module "sgacl_{al}" {{',
            f'  source    = "{_SGACL_MODULE_SRC}"',
            f"  providers = {{ huaweicloud = huaweicloud.{al} }}",
            "",
            f'  security_groups = var.secgroups["{a}"].groups',
            f'  sg_rules        = var.secgroups["{a}"].rules',
            "}",
            "",
            f'output "secgroup_ids_{al}" {{',
            f"  value = module.sgacl_{al}.secgroup_ids",
            "}",
            "",
        ]

    write_generated(env_dir, (
        ("providers.generated.tf", prov),
        ("sgacl.generated.tf", calls),
    ))
