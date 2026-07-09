"""Deterministic structural detectors.

Each detector walks the graph and emits RawSignals - one per affected
resource, the way a scanner would - but crucially tags each signal with
the *root node* that structurally generates it, and records the exact
traversal as a ReasoningStep list. The LLM never invents findings; it
only clusters and explains what these detectors surface. That split is
deliberate: detection must be reproducible and auditable, prose doesn't.
"""

from __future__ import annotations

from typing import Callable, Iterator

from ..graph import EdgeType, GraphStore, Node, NodeType
from .findings import RawSignal, ReasoningStep

SENSITIVE_PORTS = {22: "ssh", 3389: "rdp", 5432: "postgres", 3306: "mysql",
                   6379: "redis", 27017: "mongodb", 9200: "elasticsearch"}

Detector = Callable[[GraphStore], Iterator[RawSignal]]


def _is_wildcardish(actions: list[str], resources: list[str]) -> list[str]:
    """Return the wildcard grants that make a policy over-permissioned."""
    wide = [a for a in actions if a == "*" or a.endswith(":*")]
    if wide and ("*" in resources or not resources):
        return wide
    return []


def detect_wildcard_iam(store: GraphStore) -> Iterator[RawSignal]:
    """Policy with service-wildcard actions on Resource:* -> one signal per
    principal that ends up holding that permission."""
    for policy in store.nodes(NodeType.IAM_POLICY):
        wide = _is_wildcardish(policy.props.get("actions", []),
                               policy.props.get("resources", []))
        if not wide:
            continue
        for role_edge in store.out_edges(policy.id, EdgeType.ATTACHED_TO):
            role = store.get_node(role_edge.dst)
            if role is None:
                continue
            principals = store.in_edges(role.id, EdgeType.ASSUMES)
            for pe in principals:
                principal = store.get_node(pe.src)
                if principal is None:
                    continue
                yield RawSignal(
                    id=f"wildcard_iam:{principal.id}",
                    rule="wildcard_iam",
                    severity="high",
                    resource=principal.id,
                    root_node=policy.id,
                    message=f"{principal.name} ({principal.type.value}) holds "
                            f"{', '.join(wide)} on all resources via "
                            f"{role.name} <- {policy.name}",
                    evidence={"wildcard_actions": wide, "role": role.id,
                              "policy": policy.id},
                    trace=[
                        ReasoningStep(policy.id, None,
                                      f"policy grants {', '.join(wide)} on Resource:*"),
                        ReasoningStep(role.id, EdgeType.ATTACHED_TO.value,
                                      "policy is attached to this role"),
                        ReasoningStep(principal.id, EdgeType.ASSUMES.value,
                                      "this principal assumes the role, inheriting the grant"),
                    ],
                )


def detect_open_security_group(store: GraphStore) -> Iterator[RawSignal]:
    """SG open to 0.0.0.0/0 on a sensitive port -> one signal per service
    sitting behind it."""
    for sg in store.nodes(NodeType.SECURITY_GROUP):
        open_rules = [r for r in sg.props.get("rules", [])
                      if r.get("cidr") == "0.0.0.0/0" and r.get("port") in SENSITIVE_PORTS]
        if not open_rules:
            continue
        ports = sorted({r["port"] for r in open_rules})
        portlist = ", ".join(f"{p} ({SENSITIVE_PORTS[p]})" for p in ports)
        for e in store.in_edges(sg.id, EdgeType.GUARDED_BY):
            svc = store.get_node(e.src)
            if svc is None:
                continue
            yield RawSignal(
                id=f"open_sg:{svc.id}",
                rule="open_security_group",
                severity="critical",
                resource=svc.id,
                root_node=sg.id,
                message=f"{svc.name} is reachable from the internet on {portlist} "
                        f"via security group {sg.name}",
                evidence={"ports": ports, "security_group": sg.id,
                          "description": sg.props.get("description", "")},
                trace=[
                    ReasoningStep(sg.id, None,
                                  f"security group allows 0.0.0.0/0 on {portlist}"),
                    ReasoningStep(svc.id, EdgeType.GUARDED_BY.value,
                                  "this service is placed behind that group"),
                ],
            )


def detect_public_bucket(store: GraphStore) -> Iterator[RawSignal]:
    """Publicly readable bucket -> a signal for the bucket, plus one per
    service writing (potentially sensitive) data into it."""
    for bucket in store.nodes(NodeType.S3_BUCKET):
        exposed = store.out_edges(bucket.id, EdgeType.EXPOSED_TO)
        if not (bucket.props.get("public") or exposed):
            continue
        base_trace = [ReasoningStep(bucket.id, None,
                                    "bucket policy allows public read (Principal:*)")]
        yield RawSignal(
            id=f"public_bucket:{bucket.id}",
            rule="public_bucket",
            severity="critical",
            resource=bucket.id,
            root_node=bucket.id,
            message=f"s3 bucket {bucket.name} is publicly readable",
            evidence={"contains_pii": bucket.props.get("contains_pii", False)},
            trace=list(base_trace),
        )
        for e in store.in_edges(bucket.id, EdgeType.WRITES):
            writer = store.get_node(e.src)
            if writer is None:
                continue
            yield RawSignal(
                id=f"public_bucket_writer:{writer.id}:{bucket.id}",
                rule="public_bucket",
                severity="critical",
                resource=writer.id,
                root_node=bucket.id,
                message=f"{writer.name} writes data into publicly readable "
                        f"bucket {bucket.name}"
                        + (f" ({e.props['data']})" if e.props.get("data") else ""),
                evidence={"bucket": bucket.id, "data": e.props.get("data", "unknown")},
                trace=base_trace + [
                    ReasoningStep(writer.id, EdgeType.WRITES.value,
                                  "this service writes into the exposed bucket"),
                ],
            )


def detect_ci_secret_boundary(store: GraphStore) -> Iterator[RawSignal]:
    """Pipeline steps authenticating to the cloud with a shared long-lived
    secret (instead of OIDC) -> one signal per pipeline step."""
    for secret in store.nodes(NodeType.SECRET):
        kind = str(secret.props.get("kind", "")).lower()
        if "long-lived" not in kind and "access key" not in kind:
            continue
        for e in store.in_edges(secret.id, EdgeType.USES_SECRET):
            step = store.get_node(e.src)
            if step is None or step.type != NodeType.PIPELINE_STEP:
                continue
            # does this step also assume a role? how wide is it?
            assumed = store.neighbors_via(step.id, EdgeType.ASSUMES)
            role_note = ""
            for role in assumed:
                for pe in store.in_edges(role.id, EdgeType.ATTACHED_TO):
                    pol = store.get_node(pe.src)
                    if pol and _is_wildcardish(pol.props.get("actions", []),
                                               pol.props.get("resources", [])):
                        role_note = f" and that key maps to {role.name} with {pol.name}"
            yield RawSignal(
                id=f"ci_secret:{step.id}",
                rule="ci_long_lived_secret",
                severity="high",
                resource=step.id,
                root_node=secret.id,
                message=f"pipeline step {step.name} authenticates with long-lived "
                        f"secret {secret.name}{role_note}",
                evidence={"secret": secret.id,
                          "rotated": secret.props.get("rotated", "unknown"),
                          "assumed_roles": [r.id for r in assumed]},
                trace=[
                    ReasoningStep(secret.id, None,
                                  f"long-lived credential ({secret.props.get('kind','')}), "
                                  f"last rotated {secret.props.get('rotated', 'unknown')}"),
                    ReasoningStep(step.id, EdgeType.USES_SECRET.value,
                                  "this CI step injects the credential"),
                ] + [ReasoningStep(r.id, EdgeType.ASSUMES.value,
                                   "the credential maps to this cloud role")
                     for r in assumed],
            )


def detect_single_point_of_failure(store: GraphStore,
                                   min_callers: int = 5) -> Iterator[RawSignal]:
    """Service that a large share of the estate calls directly. Not a
    vulnerability by itself - it's an architectural risk amplifier, and it
    matters for prioritizing everything else."""
    for svc in store.nodes(NodeType.SERVICE):
        callers = [e.src for e in store.in_edges(svc.id, EdgeType.CALLS)]
        if len(callers) < min_callers:
            continue
        yield RawSignal(
            id=f"spof:{svc.id}",
            rule="single_point_of_failure",
            severity="medium",
            resource=svc.id,
            root_node=svc.id,
            message=f"{svc.name} is called directly by {len(callers)} services; "
                    f"a compromise or outage here propagates estate-wide",
            evidence={"callers": callers},
            trace=[ReasoningStep(svc.id, None,
                                 f"{len(callers)} inbound call edges "
                                 f"({len(callers)}/{sum(1 for _ in store.nodes(NodeType.SERVICE))} services)")]
                  + [ReasoningStep(c, EdgeType.CALLS.value, "direct caller")
                     for c in callers[:8]],
        )


ALL_DETECTORS: list[Detector] = [
    detect_wildcard_iam,
    detect_open_security_group,
    detect_public_bucket,
    detect_ci_secret_boundary,
    detect_single_point_of_failure,
]


def run_all(store: GraphStore) -> list[RawSignal]:
    signals: list[RawSignal] = []
    for det in ALL_DETECTORS:
        signals.extend(det(store))
    return signals
