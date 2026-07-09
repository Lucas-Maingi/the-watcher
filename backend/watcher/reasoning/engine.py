"""The reasoning engine: signals in, clustered root causes out.

Pipeline:
  1. run deterministic detectors  -> flat RawSignals (the "scanner view")
  2. cluster by root_node         -> one candidate finding per structural cause
  3. blast radius per cluster     -> exact scope from the graph, banded effort
  4. narrative pass               -> Claude if a key is present, template if not

Same class serves the CLI, the HTTP API and the agent tools - it's the
one front door to the product's actual IP.
"""

from __future__ import annotations

import hashlib

from ..graph import GraphStore
from . import blast_radius, detectors, llm
from .findings import RawSignal, ReasoningStep, RootCauseFinding

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# per-rule framing for the clustered finding. The detector knows the shape
# of the problem; this knows how to talk about it as a root cause.
_RULE_FRAMING: dict[str, dict[str, str]] = {
    "wildcard_iam": {
        "title": "Shared over-permissioned IAM policy pattern",
        "description": ("A single IAM policy granting service-level wildcards on all "
                        "resources is attached to a role assumed by many workloads. Every "
                        "workload inherits far more permission than it uses, so one "
                        "compromised function is an account-wide incident."),
        "recommendation": ("Split into per-service roles with policies scoped to what each "
                           "service actually calls (derive from CloudTrail / IAM Access "
                           "Analyzer). Fix the template it comes from, not the instances."),
    },
    "open_security_group": {
        "title": "Internet-exposed admin/database ports via shared security group",
        "description": ("A security group opens sensitive ports to 0.0.0.0/0 and multiple "
                        "services sit behind it - the exposure multiplies with every service "
                        "that reuses the group."),
        "recommendation": ("Remove the open rules (check flow logs for legitimate use first), "
                           "and stop reusing ad-hoc groups across services."),
    },
    "public_bucket": {
        "title": "Publicly readable bucket receiving internal data",
        "description": ("A bucket with a public-read policy is a live data-exposure path; "
                        "services are actively writing into it, so this is leaking now, not "
                        "hypothetically."),
        "recommendation": ("Enable the public access block, replace public read with "
                           "presigned URLs or CloudFront+OAC for the legitimate consumers."),
    },
    "ci_long_lived_secret": {
        "title": "CI deploys authenticate with a shared long-lived cloud key",
        "description": ("Most pipelines deploy using one long-lived AWS access key stored as "
                        "a shared CI secret. Anyone with repo write access - or any exfil of "
                        "CI logs/env - holds standing cloud credentials."),
        "recommendation": ("Migrate to GitHub OIDC federation with short-lived, per-repo "
                           "role assumption; then delete the key."),
    },
    "single_point_of_failure": {
        "title": "Architectural single point of failure",
        "description": ("One service sits on nearly every call path in the estate. Its "
                        "security posture bounds everyone else's, and it amplifies the "
                        "blast radius of every other finding that touches it."),
        "recommendation": ("Not a ticket - a roadmap item. Short term: prioritize hardening "
                           "this service above the rest of the backlog."),
    },
}


def _finding_id(root_node: str, rule: str) -> str:
    return "rc_" + hashlib.sha1(f"{rule}|{root_node}".encode()).hexdigest()[:10]


class ReasoningEngine:
    def __init__(self, store: GraphStore, use_llm: bool = True) -> None:
        self.store = store
        self.use_llm = use_llm

    def raw_signals(self) -> list[RawSignal]:
        """The 'before' picture: what a conventional scanner would show."""
        return detectors.run_all(self.store)

    def root_causes(self) -> list[RootCauseFinding]:
        signals = self.raw_signals()

        # cluster: same structural root + same rule = same disease
        clusters: dict[tuple[str, str], list[RawSignal]] = {}
        for sig in signals:
            clusters.setdefault((sig.root_node, sig.rule), []).append(sig)

        findings: list[RootCauseFinding] = []
        for (root, rule), sigs in clusters.items():
            framing = _RULE_FRAMING.get(rule, {})
            severity = min((s.severity for s in sigs), key=lambda s: _SEV_ORDER[s])
            root_n = self.store.get_node(root)
            title = framing.get("title", rule)
            if root_n is not None:
                title = f"{title} ({root_n.name})"

            # merged trace: root first, then each distinct hop once, in order
            seen_steps: set[tuple[str, str | None]] = set()
            trace: list[ReasoningStep] = []
            for s in sigs:
                for step in s.trace:
                    key = (step.node, step.edge)
                    if key not in seen_steps:
                        seen_steps.add(key)
                        trace.append(step)

            f = RootCauseFinding(
                id=_finding_id(root, rule),
                title=title,
                severity=severity,
                root_node=root,
                description=framing.get("description", ""),
                recommendation=framing.get("recommendation", ""),
                signals=sorted(sigs, key=lambda s: s.id),
                trace=trace,
                blast_radius=blast_radius.estimate(self.store, root, sigs),
            )
            findings.append(f)

        findings.sort(key=lambda f: (_SEV_ORDER[f.severity], -f.signal_count))

        for f in findings:
            d = f.to_dict()
            f.narrative = (llm.narrate(d) if self.use_llm else None) or \
                          llm.template_narrative(d)

        return findings
