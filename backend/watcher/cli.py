"""CLI entry point. Deliberately boring argparse - this is plumbing.

  watcher ingest --demo                     # build the Brightpath demo graph
  watcher ingest --github ORG --token ...   # ingest a real GitHub org
  watcher ingest --aws                      # ingest AWS via ambient credentials
  watcher summary                           # node/edge counts
  watcher query nodes --type iam_role       # list nodes
  watcher query node <id>                   # one node + its edges
  watcher query path <src> <dst>            # shortest path between two nodes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .graph import GraphStore, NodeType

DEFAULT_GRAPH = Path(os.environ.get("WATCHER_GRAPH", "data/graph.json"))


def _load() -> GraphStore:
    if not DEFAULT_GRAPH.exists():
        sys.exit(f"no graph at {DEFAULT_GRAPH} - run `watcher ingest --demo` first")
    return GraphStore.load(DEFAULT_GRAPH)


def cmd_ingest(args: argparse.Namespace) -> None:
    store = GraphStore.load(DEFAULT_GRAPH) if (args.merge and DEFAULT_GRAPH.exists()) else GraphStore()

    ran_something = False
    if args.demo:
        from .ingest.demo import generate
        generate(store)
        ran_something = True
    if args.github:
        from .ingest.github_connector import GitHubConnector
        token = args.token or os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("need --token or GITHUB_TOKEN for github ingestion")
        GitHubConnector(token).ingest_org(args.github, store, limit=args.limit)
        ran_something = True
    if args.aws:
        from .ingest.aws_connector import AWSConnector
        AWSConnector(profile=args.profile).ingest(store)
        ran_something = True

    if not ran_something:
        sys.exit("nothing to ingest: pass --demo, --github ORG, and/or --aws")

    store.save(DEFAULT_GRAPH)
    print(f"graph saved to {DEFAULT_GRAPH}")
    print(json.dumps(store.summary(), indent=2))


def cmd_summary(_: argparse.Namespace) -> None:
    print(json.dumps(_load().summary(), indent=2))


def cmd_query(args: argparse.Namespace) -> None:
    store = _load()
    if args.what == "nodes":
        ntype = NodeType(args.type) if args.type else None
        for n in store.nodes(ntype):
            print(f"{n.id:60s} {n.name}")
    elif args.what == "node":
        n = store.get_node(args.id)
        if not n:
            sys.exit(f"no node {args.id}")
        print(json.dumps(n.to_dict(), indent=2))
        for e in store.out_edges(args.id):
            print(f"  --[{e.type.value}]--> {e.dst}")
        for e in store.in_edges(args.id):
            print(f"  <--[{e.type.value}]-- {e.src}")
    elif args.what == "path":
        path = store.shortest_path(args.id, args.dst)
        print(" -> ".join(path) if path else "no path")


def main() -> None:
    p = argparse.ArgumentParser(prog="watcher", description="architectural security intelligence")
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="build/extend the graph")
    ing.add_argument("--demo", action="store_true", help="generate the Brightpath demo dataset")
    ing.add_argument("--github", metavar="ORG", help="ingest a GitHub org/user")
    ing.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN)")
    ing.add_argument("--limit", type=int, default=30, help="max repos to ingest from GitHub")
    ing.add_argument("--aws", action="store_true", help="ingest AWS via boto3 credentials")
    ing.add_argument("--profile", help="AWS profile name")
    ing.add_argument("--merge", action="store_true", help="merge into existing graph instead of replacing")
    ing.set_defaults(func=cmd_ingest)

    sm = sub.add_parser("summary", help="graph stats")
    sm.set_defaults(func=cmd_summary)

    q = sub.add_parser("query", help="poke at the graph")
    qsub = q.add_subparsers(dest="what", required=True)
    qn = qsub.add_parser("nodes")
    qn.add_argument("--type", choices=[t.value for t in NodeType])
    q1 = qsub.add_parser("node")
    q1.add_argument("id")
    qp = qsub.add_parser("path")
    qp.add_argument("id")
    qp.add_argument("dst")
    q.set_defaults(func=cmd_query)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
