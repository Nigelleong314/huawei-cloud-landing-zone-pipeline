"""Cross-env shared-resource ownership registry.

deps.json captures remote-state edges, but some cross-env dependencies flow
through NAME-BASED data-source lookups that no state reference reveals. Those
are exactly the dependencies that caused the historical 06/07 double-apply:
nothing structural said who owned the DNS query-log LTS infrastructure.

Every cross-env shared resource is declared here with its owner env and the
mechanism consumers use. check() enforces owner-before-consumer ordering
(LZR-008 extension); verify runs it, so a future ownership inversion is a
build failure instead of a deployment discovery.
"""

from .helpers import ENV_NAMES

SHARED_RESOURCES = [
    {
        "id": "dns-query-log-lts",
        "resource": "LTS log group + stream receiving DNS resolver query logs",
        "owner": "06-observability",
        "consumers": ["08-network-dns"],
        "mechanism": ("06-observability emits the owned huaweicloud_lts_group/_stream "
                      "from the 08_DNS AccessLogs rows; the dns module runs with "
                      "manage_query_log_infra=false and resolves them by name via "
                      "huaweicloud_lts_groups/_streams data sources"),
    },
    {
        "id": "flow-log-lts-groups",
        "resource": "Per-VPC flow-log LTS groups/streams (<vpc>-flowlog)",
        "owner": "05-network",
        "consumers": ["06-observability"],
        "mechanism": ("the network module creates one group/stream per VPC when "
                      "enable_vpc_flow_logs is on; 06-observability's log-converge "
                      "codegen resolves them per account by name via data sources"),
    },
    {
        "id": "cfw-lts-streams",
        "resource": "CFW traffic/access/attack LTS streams",
        "owner": "05-network",
        "consumers": ["06-observability"],
        "mechanism": ("the network module's CFW instance creates the streams (names "
                      "from the CloudFirewall sheet); log-converge rows reference "
                      "them by name"),
    },
    {
        "id": "smn-alarm-topics",
        "resource": "SMN topics used for alarm notifications",
        "owner": "06-observability",
        "consumers": ["07-security"],
        "mechanism": ("edge-protection resolves topic NAMES via the smn_topics data "
                      "source for Anti-DDoS alarm bindings; 07-security also reads "
                      "06 outputs via remote state"),
    },
]


def check(env_names=None) -> list:
    """Ordering/consistency errors for the registry (empty = OK)."""
    envs = set(env_names or ENV_NAMES)
    errs = []
    seen = set()
    for r in SHARED_RESOURCES:
        if r["id"] in seen:
            errs.append(f"ownership: duplicate id {r['id']!r}")
        seen.add(r["id"])
        if r["owner"] not in envs:
            errs.append(f"ownership[{r['id']}]: owner {r['owner']!r} is not an env")
        for c in r["consumers"]:
            if c not in envs:
                errs.append(f"ownership[{r['id']}]: consumer {c!r} is not an env")
            elif not r["owner"] < c:
                errs.append(f"ownership[{r['id']}]: owner {r['owner']} does not sort "
                            f"before consumer {c} - one-pass apply order is broken")
    return errs


def edges() -> list:
    """(owner, consumer) pairs - the apply-order edges data lookups imply."""
    out = []
    for r in SHARED_RESOURCES:
        for c in r["consumers"]:
            out.append((r["owner"], c))
    return out
