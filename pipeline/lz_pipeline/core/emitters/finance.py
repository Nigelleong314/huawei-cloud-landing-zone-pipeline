"""02-finance: per-account enterprise-project fan-out."""

from pathlib import Path
from ..helpers import MODULE_SOURCE_ROOT, _acct_alias
from ..builders import _cost_centers_by_account
from ..templating import render_lines
from ..writer import write_generated
from .common import _provider_alias_block


_FINANCIAL_MODULE_SRC = MODULE_SOURCE_ROOT + "/financial"


def _emit_finance_codegen(env_dir: Path, spec: dict):
    """Generate per-account provider aliases + cost-center module calls.

    One module call per target account, each passing that account's subset of
    cost centers (var.cost_centers_by_account["<account>"]). Master uses the
    default provider; every other account gets an alias.
    """
    by_acct = _cost_centers_by_account(spec)
    accounts = list(by_acct.keys())                       # preserves first-seen order
    non_master = [a for a in accounts if a != "master"]

    prov = [
        "# --- Account providers ---",
        "",
    ]
    for a in non_master:
        prov += _provider_alias_block(a)

    calls = [
        "# --- Cost-center projects by account ---",
        "",
    ]
    def _mod(a):
        return "cost_centers_master" if a == "master" else f"cost_centers_{_acct_alias(a)}"

    for a in accounts:
        providers_line = "" if a == "master" else \
            f"  providers = {{ huaweicloud = huaweicloud.{_acct_alias(a)} }}\n"
        calls.append(f"# Account: {'Master' if a == 'master' else a}")
        calls += render_lines("finance_module_call.tf.tmpl",
                              module_name=_mod(a), src=_FINANCIAL_MODULE_SRC,
                              providers_line=providers_line, account=a) + [""]

    outs = [
        "# --- Cost-center project outputs by account ---",
        "",
        'output "cost_center_ep_ids_by_account" {',
        "  description = \"Map of account -> { cost-center EP name -> EP ID }.\"",
        "  value = {",
    ]
    for a in accounts:
        outs.append(f'    "{a}" = module.{_mod(a)}.cost_center_ep_ids')
    outs += ["  }", "}", ""]

    write_generated(env_dir, (
        ("providers.generated.tf", prov),
        ("cost-centers.generated.tf", calls),
        ("outputs.generated.tf", outs),
    ))
