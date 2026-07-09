"""Graph store: NetworkX MultiDiGraph behind a small interface.

This is deliberately the only module that touches networkx directly.
If the project ever outgrows an in-process graph, this file is the
swap point — nothing above it knows what's underneath.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import networkx as nx

from .model import Edge, EdgeType, Node, NodeType


class GraphStore:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    # ---------- mutation ----------

    def add_node(self, node: Node) -> None:
        # idempotent: same id merges props instead of duplicating.
        # (an edge added before its endpoint makes networkx create a bare
        # attribute-less node - treat that as "not really there yet")
        if self.g.has_node(node.id) and "props" in self.g.nodes[node.id]:
            self.g.nodes[node.id]["props"].update(node.props)
        else:
            self.g.add_node(node.id, type=node.type, name=node.name, props=dict(node.props))

    def add_edge(self, edge: Edge) -> None:
        # one edge per (src, dst, type); re-adding updates props
        key = edge.type.value
        if self.g.has_edge(edge.src, edge.dst, key=key):
            self.g.edges[edge.src, edge.dst, key]["props"].update(edge.props)
        else:
            self.g.add_edge(edge.src, edge.dst, key=key, type=edge.type, props=dict(edge.props))

    # ---------- lookup ----------

    def get_node(self, node_id: str) -> Node | None:
        if not self.g.has_node(node_id):
            return None
        d = self.g.nodes[node_id]
        return Node(id=node_id, type=d["type"], name=d["name"], props=d["props"])

    def nodes(self, ntype: NodeType | None = None) -> Iterator[Node]:
        for nid, d in self.g.nodes(data=True):
            if ntype is None or d["type"] == ntype:
                yield Node(id=nid, type=d["type"], name=d["name"], props=d["props"])

    def edges(self, etype: EdgeType | None = None) -> Iterator[Edge]:
        for src, dst, d in self.g.edges(data=True):
            if etype is None or d["type"] == etype:
                yield Edge(src=src, dst=dst, type=d["type"], props=d["props"])

    def out_edges(self, node_id: str, etype: EdgeType | None = None) -> list[Edge]:
        if not self.g.has_node(node_id):
            return []
        return [
            Edge(src=s, dst=t, type=d["type"], props=d["props"])
            for s, t, d in self.g.out_edges(node_id, data=True)
            if etype is None or d["type"] == etype
        ]

    def in_edges(self, node_id: str, etype: EdgeType | None = None) -> list[Edge]:
        if not self.g.has_node(node_id):
            return []
        return [
            Edge(src=s, dst=t, type=d["type"], props=d["props"])
            for s, t, d in self.g.in_edges(node_id, data=True)
            if etype is None or d["type"] == etype
        ]

    def neighbors_via(self, node_id: str, etype: EdgeType, reverse: bool = False) -> list[Node]:
        edges = self.in_edges(node_id, etype) if reverse else self.out_edges(node_id, etype)
        ids = [e.src if reverse else e.dst for e in edges]
        return [n for nid in ids if (n := self.get_node(nid)) is not None]

    # ---------- traversal ----------

    def reachable_from(self, node_id: str, via: set[EdgeType] | None = None,
                       max_depth: int = 6) -> set[str]:
        """BFS over selected edge types. Used for blast radius and trust paths."""
        seen: set[str] = set()
        frontier = [node_id]
        depth = 0
        while frontier and depth < max_depth:
            nxt: list[str] = []
            for nid in frontier:
                for e in self.out_edges(nid):
                    if via is not None and e.type not in via:
                        continue
                    if e.dst not in seen and e.dst != node_id:
                        seen.add(e.dst)
                        nxt.append(e.dst)
            frontier = nxt
            depth += 1
        return seen

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        try:
            return nx.shortest_path(self.g, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # ---------- stats ----------

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for _, d in self.g.nodes(data=True):
            by_type[d["type"].value] = by_type.get(d["type"].value, 0) + 1
        return {
            "nodes": self.g.number_of_nodes(),
            "edges": self.g.number_of_edges(),
            "nodes_by_type": dict(sorted(by_type.items())),
        }

    # ---------- persistence ----------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "nodes": [self._node_dict(nid) for nid in self.g.nodes],
            "edges": [
                {"src": s, "dst": t, "type": d["type"].value, "props": d["props"]}
                for s, t, d in self.g.edges(data=True)
            ],
        }
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    def _node_dict(self, nid: str) -> dict[str, Any]:
        d = self.g.nodes[nid]
        return {"id": nid, "type": d["type"].value, "name": d["name"], "props": d["props"]}

    @classmethod
    def load(cls, path: str | Path) -> "GraphStore":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls()
        for nd in data["nodes"]:
            store.add_node(Node.from_dict(nd))
        for ed in data["edges"]:
            store.add_edge(Edge.from_dict(ed))
        return store
