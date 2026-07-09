"""Blast radius estimation: if you fix root cause X, what does that touch?

This is heuristic, and honestly labelled as such. The service/resource
lists come straight from graph traversal so they're exact; the effort
band is a judgment call encoded in code. Bands ("hours/days/weeks")
instead of fake-precision story points - anyone who's estimated a
cross-team IAM migration knows a number would be a lie.
"""

from __future__ import annotations

from ..graph import EdgeType, GraphStore, NodeType
from .findings import BlastRadius, RawSignal


def _owning_services(store: GraphStore, node_ids: set[str]) -> set[str]:
    """Map arbitrary affected nodes back to the services that own them."""
    services: set[str] = set()
    for nid in node_ids:
        n = store.get_node(nid)
        if n is None:
            continue
        if n.type == NodeType.SERVICE:
            services.add(n.name)
        elif n.type == NodeType.LAMBDA_FUNCTION:
            # lambda belongs to the service that depends on it
            for e in store.in_edges(nid, EdgeType.DEPENDS_ON):
                s = store.get_node(e.src)
                if s and s.type == NodeType.SERVICE:
                    services.add(s.name)
        elif n.type == NodeType.PIPELINE_STEP:
            # step -> pipeline -> repo -> service
            for e in store.in_edges(nid, EdgeType.CONTAINS):
                for e2 in store.in_edges(e.src, EdgeType.CONTAINS):
                    for e3 in store.out_edges(e2.src, EdgeType.IMPLEMENTS):
                        s = store.get_node(e3.dst)
                        if s:
                            services.add(s.name)
    return services


def estimate(store: GraphStore, root_node: str, signals: list[RawSignal]) -> BlastRadius:
    affected = {s.resource for s in signals}
    services = _owning_services(store, affected)
    root = store.get_node(root_node)
    rtype = root.type if root else None
    n = len(services)

    if rtype == NodeType.IAM_POLICY:
        effort = "days" if n > 3 else "hours"
        detail = (f"replace one shared policy with {n} scoped per-service policies; "
                  f"mechanical but each service needs its actual permission set derived "
                  f"(CloudTrail Access Analyzer helps)")
        risk = ("under-scoping breaks runtime calls that the old wildcard silently allowed; "
                "roll out with permission analyzer data, one service at a time")
    elif rtype == NodeType.SECURITY_GROUP:
        effort = "hours"
        detail = (f"tighten one security group; {n} services sit behind it, "
                  f"verify none legitimately need the open ports first")
        risk = ("anything actually depending on public access to those ports breaks "
                "immediately - check flow logs before closing")
    elif rtype == NodeType.S3_BUCKET:
        effort = "hours"
        detail = ("flip public access block + fix bucket policy; then decide how the "
                  "legitimate consumers of the exports get access (presigned urls?)")
        risk = ("whoever currently downloads these exports (customers? a partner?) "
                "loses access the moment it closes - find them before, not after")
    elif rtype == NodeType.SECRET:
        effort = "days" if n > 5 else "hours"
        detail = (f"move {n} repos' deploy jobs from a shared long-lived key to "
                  f"GitHub OIDC federation; one reusable workflow makes it mostly copy-paste")
        risk = ("deploys fail if the OIDC trust policy conditions are wrong; migrate one "
                "low-stakes repo first, keep the old key until the last repo cuts over")
    elif rtype == NodeType.SERVICE:
        # for a SPOF the blast radius IS the caller set, not just the node itself
        for sig in signals:
            for caller in sig.evidence.get("callers", []):
                affected.add(caller)
        services = _owning_services(store, affected)
        n = len(services)
        effort = "weeks"
        detail = (f"reducing a single point of failure is an architecture project, not a "
                  f"ticket; {n - 1} direct callers to consider")
        risk = "high - this is a redesign; treat it as a roadmap item, not a fix"
    else:
        effort = "days"
        detail = f"{n} services affected"
        risk = "unassessed"

    return BlastRadius(
        services_touched=sorted(services),
        resources_touched=sorted(affected),
        effort=effort,
        effort_detail=detail,
        breakage_risk=risk,
    )
