"""HTTP API. Thin on purpose - every endpoint is a wrapper over
watcher.tools, which is the single front door to the reasoning engine.
If the dashboard can see it, an agent can see it, and vice versa.

Run:  uvicorn watcher.api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .. import tools
from ..graph import NodeType

app = FastAPI(
    title="The Watcher",
    description="Architectural security intelligence: root causes, not alert noise.",
    version="0.1.0",
)

# local dev: the vite dashboard runs on another port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "graph": str(tools.DEFAULT_GRAPH)}


@app.get("/api/summary")
def summary() -> dict:
    store = tools._engine().store
    findings = tools._findings()
    raw = tools._engine().raw_signals()
    return {
        "graph": store.summary(),
        "raw_findings": len(raw),
        "root_causes": len(findings),
        "noise_reduction": f"{len(raw)} -> {len(findings)}",
    }


@app.get("/api/root-causes")
def root_causes(severity: str | None = None) -> list[dict]:
    return tools.get_root_causes(severity)


@app.get("/api/root-causes/{finding_id}")
def finding_detail(finding_id: str) -> dict:
    result = tools.explain_finding(finding_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/api/root-causes/{finding_id}/blast-radius")
def blast_radius(finding_id: str) -> dict:
    result = tools.get_blast_radius(finding_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/api/raw-findings")
def raw_findings() -> list[dict]:
    """The 'before' view: flat scanner-style alerts. Exists mostly to
    power the before/after demo moment."""
    return [s.to_dict() for s in tools._engine().raw_signals()]


@app.get("/api/context")
def context(name: str) -> dict:
    return tools.get_context_for(name)


@app.get("/api/graph/nodes")
def graph_nodes(type: str | None = None) -> list[dict]:
    ntype = NodeType(type) if type else None
    return [n.to_dict() for n in tools._engine().store.nodes(ntype)]


@app.get("/api/graph/node/{node_id:path}")
def graph_node(node_id: str) -> dict:
    store = tools._engine().store
    n = store.get_node(node_id)
    if n is None:
        raise HTTPException(404, f"no node {node_id}")
    return {
        "node": n.to_dict(),
        "out": [e.to_dict() for e in store.out_edges(node_id)],
        "in": [e.to_dict() for e in store.in_edges(node_id)],
    }
