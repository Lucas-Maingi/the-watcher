"""Agent tool interface - the functions an AI coding agent calls.

This is the agent-native surface of the product. Four tools, each
returning plain JSON-able dicts, documented well enough that a model
can use them from the schema alone. The MCP server and the HTTP API
are both thin wrappers over this module; there is no logic here that
the dashboard can't also reach.

Design rule: results must carry enough context to act on WITHOUT
another round trip. An agent asking "what affects the file I'm editing"
gets the root cause, the fix, and the blast radius in one shot.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

from .graph import GraphStore, NodeType
from .reasoning import ReasoningEngine

DEFAULT_GRAPH = Path(os.environ.get("WATCHER_GRAPH", "data/graph.json"))


@functools.lru_cache(maxsize=1)
def _engine() -> ReasoningEngine:
    # narratives are computed lazily and cached with the engine; agents
    # don't wait on the LLM unless a key is configured
    return ReasoningEngine(GraphStore.load(DEFAULT_GRAPH),
                           use_llm=bool(os.environ.get("ANTHROPIC_API_KEY")))


@functools.lru_cache(maxsize=1)
def _findings():
    return _engine().root_causes()


def reset_cache() -> None:
    _engine.cache_clear()
    _findings.cache_clear()


# ---------------------------------------------------------------- tools

def get_root_causes(severity: str | None = None) -> list[dict[str, Any]]:
    """List clustered root-cause findings, most severe first.

    Args:
        severity: optional filter - "critical", "high", "medium" or "low".

    Returns a summary per finding (id, title, severity, how many raw
    scanner findings it explains, fix effort). Use explain_finding(id)
    for the full reasoning trace and narrative.
    """
    out = []
    for f in _findings():
        if severity and f.severity != severity:
            continue
        out.append({
            "id": f.id, "title": f.title, "severity": f.severity,
            "explains_findings": f.signal_count,
            "fix_effort": f.blast_radius.effort,
            "services_touched": len(f.blast_radius.services_touched),
            "recommendation": f.recommendation,
        })
    return out


def explain_finding(finding_id: str) -> dict[str, Any]:
    """Full detail for one root-cause finding: description, narrative,
    the complete reasoning trace (which graph nodes/edges led to this
    conclusion), every raw signal it explains, blast radius, and the
    compliance controls it maps to.

    Args:
        finding_id: the id from get_root_causes, e.g. "rc_ab12cd34ef".
    """
    for f in _findings():
        if f.id == finding_id:
            return f.to_dict()
    return {"error": f"no finding {finding_id}",
            "available": [f.id for f in _findings()]}


def get_blast_radius(finding_id: str) -> dict[str, Any]:
    """What fixing this root cause touches: exact service and resource
    lists (from graph traversal), a banded effort estimate, and what is
    likely to break while applying the fix.

    Args:
        finding_id: the id from get_root_causes.
    """
    for f in _findings():
        if f.id == finding_id:
            return {"id": f.id, "title": f.title, **f.blast_radius.to_dict()}
    return {"error": f"no finding {finding_id}"}


def get_context_for(name: str) -> dict[str, Any]:
    """Root-cause context for a repo/service/file an agent is working on.

    Args:
        name: a service or repo name ("payments-service"), or a file path
            containing one ("services/payments-service/handler.py") - the
            longest matching service name wins.

    Returns the matched service plus every root cause whose blast radius
    includes it, so a coding agent editing that code knows which
    architectural problems it can fix (or should avoid worsening) there.
    """
    store = _engine().store
    known = sorted((n.name for n in store.nodes(NodeType.SERVICE)), key=len, reverse=True)
    needle = name.replace("\\", "/").lower()
    match = next((k for k in known if k.lower() in needle or needle in k.lower()), None)
    if match is None:
        return {"error": f"couldn't map {name!r} to a known service",
                "known_services": sorted(known)}

    relevant = [
        {"id": f.id, "title": f.title, "severity": f.severity,
         "why_it_applies_here": next(
             (s.message for s in f.signals
              if match in s.resource or match in s.message), f.description),
         "recommendation": f.recommendation,
         "fix_effort": f.blast_radius.effort}
        for f in _findings()
        if match in f.blast_radius.services_touched
    ]
    return {"service": match, "root_causes": relevant,
            "note": "these are architectural causes, not per-file lint findings"}


TOOLS = [get_root_causes, explain_finding, get_blast_radius, get_context_for]
