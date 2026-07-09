"""Finding types.

Two levels, and the distinction is the whole product:

- RawSignal: what a conventional scanner would emit. One per affected
  resource. The demo dataset produces ~40 of these.
- RootCauseFinding: what we actually show. One per *structural cause*,
  carrying the signals it explains, the graph elements the reasoning
  walked (the trace), a blast radius estimate, and a narrative.

Every RawSignal knows its `root_node` - the graph node that structurally
generates it. That's the clustering key: signals sharing a root node are
symptoms of the same disease.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawSignal:
    id: str
    rule: str                 # detector that fired, e.g. "wildcard_iam"
    severity: str             # low | medium | high | critical
    resource: str             # node id of the affected resource
    root_node: str            # node id of the structural cause
    message: str              # scanner-style one-liner
    evidence: dict[str, Any] = field(default_factory=dict)
    trace: list["ReasoningStep"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "rule": self.rule, "severity": self.severity,
            "resource": self.resource, "root_node": self.root_node,
            "message": self.message, "evidence": self.evidence,
            "trace": [t.to_dict() for t in self.trace],
        }


@dataclass
class ReasoningStep:
    """One hop of graph reasoning: 'I looked at X, followed edge E, saw Y'.
    The dashboard renders these as the expandable 'why' - this is the
    anti-black-box guarantee, so keep them honest and machine-checkable:
    every node/edge named here must exist in the graph."""
    node: str
    edge: str | None          # edge type followed to get here, None for the starting node
    note: str                 # human-readable: what this hop established

    def to_dict(self) -> dict[str, Any]:
        return {"node": self.node, "edge": self.edge, "note": self.note}


@dataclass
class BlastRadius:
    services_touched: list[str]
    resources_touched: list[str]
    effort: str               # "hours" | "days" | "weeks"
    effort_detail: str        # why that estimate
    breakage_risk: str        # what could go wrong applying the fix

    def to_dict(self) -> dict[str, Any]:
        return {
            "services_touched": self.services_touched,
            "resources_touched": self.resources_touched,
            "effort": self.effort, "effort_detail": self.effort_detail,
            "breakage_risk": self.breakage_risk,
        }


@dataclass
class RootCauseFinding:
    id: str
    title: str
    severity: str
    root_node: str
    description: str          # what the structural problem is
    recommendation: str       # the one fix that clears the cluster
    signals: list[RawSignal]  # every scanner-style alert this explains
    trace: list[ReasoningStep]
    blast_radius: BlastRadius
    narrative: str = ""       # "how we got here" story, filled by the LLM pass
    compliance: list[dict[str, str]] = field(default_factory=list)

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "severity": self.severity,
            "root_node": self.root_node, "description": self.description,
            "recommendation": self.recommendation,
            "signal_count": self.signal_count,
            "signals": [s.to_dict() for s in self.signals],
            "trace": [t.to_dict() for t in self.trace],
            "blast_radius": self.blast_radius.to_dict(),
            "narrative": self.narrative,
            "compliance": self.compliance,
        }
