"""Provider fan-out blocks shared by the per-env emitters.

The HCL lives in core/templates/provider_*.tf.tmpl; these wrappers keep the
emitters' list-of-lines idiom (each block ends with a blank separator line).
"""
import re

from ..templating import render_lines


def _assume_role_provider(alias: str, account: str) -> list:
    """assume_role provider (temporary member AK/SK) - required when a per-account
    module creates OBS buckets, v5 IAM agencies, or org-scoped RMS in a member
    account. Shared by the config (04-perimeter) and observability (05) fan-outs."""
    return render_lines("provider_assume_role.tf.tmpl", alias=alias, account=account) + [""]


def _provider_alias_block(account: str) -> list:
    """Aliased cross-account provider block (master is the default provider).

    domain_name (the master's own domain, to scope the base token) is required
    before the agency in the member account can be assumed; agency_domain_name
    is the MEMBER account's domain (it created the agency). domain_id of the
    member is required for domain-scoped IAM ops."""
    from ..helpers import _acct_alias
    return render_lines("provider_alias.tf.tmpl",
                        alias=_acct_alias(account), account=account) + [""]


def _net_alias(name) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", str(name).strip())


def _spoke_provider_block(alias: str, account: str) -> list:
    """Cross-account provider for a spoke account (assume the member's agency with
    the master keys). Uses the assume_role BLOCK (temporary member AK/SK), not the
    agency_name attribute form: the cross-account ER attachment + RAM-share accept
    are AK/SK-signed and 404 on an agency token. default_tags IS set: the enforced
    require_mandatory_tags SCP denies untagged CREATE requests (SYS.0403)."""
    return render_lines("provider_spoke.tf.tmpl", alias=alias, account=account) + [""]
