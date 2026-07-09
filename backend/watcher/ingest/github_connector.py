"""GitHub connector. Read-only, token-auth (PAT or OAuth app token).

Pulls per repo: metadata, dependency manifests (package.json,
requirements.txt, pyproject.toml), and GitHub Actions workflows. Workflows
are parsed just deep enough to model what the reasoning layer needs:
which steps exist, which secrets they reference, whether they deploy.

Plain `requests` against the REST API - the PyGithub dependency wasn't
buying anything for four endpoints.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import requests
import yaml

from ..graph import Edge, EdgeType, GraphStore, Node, NodeType, node_id

API = "https://api.github.com"
SECRET_RE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}\}")
DEPLOY_HINTS = ("deploy", "aws-actions/configure-aws-credentials", "terraform apply",
                "cdk deploy", "sam deploy", "serverless deploy", "kubectl apply")


class GitHubConnector:
    def __init__(self, token: str) -> None:
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _get(self, path: str, **params: Any) -> Any:
        r = self.s.get(f"{API}{path}", params=params, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def _file(self, owner: str, repo: str, path: str) -> str | None:
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}")
        if not data or "content" not in data:
            return None
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")

    # ------------------------------------------------------------------

    def ingest_org(self, org: str, store: GraphStore, limit: int = 30) -> None:
        repos = self._get(f"/orgs/{org}/repos", per_page=min(limit, 100))
        if repos is None:  # not an org, try as a user
            repos = self._get(f"/users/{org}/repos", per_page=min(limit, 100)) or []
        for r in repos[:limit]:
            print(f"  ingesting {r['full_name']} ...")
            self.ingest_repo(r["owner"]["login"], r["name"], store, meta=r)

    def ingest_repo(self, owner: str, repo: str, store: GraphStore,
                    meta: dict[str, Any] | None = None) -> None:
        meta = meta or self._get(f"/repos/{owner}/{repo}") or {}
        rnode = Node(node_id(NodeType.REPOSITORY, f"{owner}/{repo}"), NodeType.REPOSITORY,
                     f"{owner}/{repo}",
                     {"language": (meta.get("language") or "").lower(),
                      "default_branch": meta.get("default_branch", "main"),
                      "private": meta.get("private", False),
                      "archived": meta.get("archived", False)})
        store.add_node(rnode)

        self._ingest_dependencies(owner, repo, rnode.id, store)
        self._ingest_workflows(owner, repo, rnode.id, store)

    def _ingest_dependencies(self, owner: str, repo: str, rid: str, store: GraphStore) -> None:
        pkg = self._file(owner, repo, "package.json")
        if pkg:
            import json as _json
            try:
                parsed = _json.loads(pkg)
                deps = {**parsed.get("dependencies", {}), **parsed.get("devDependencies", {})}
                for name, ver in deps.items():
                    self._dep(store, rid, name, str(ver))
            except ValueError:
                pass
        reqs = self._file(owner, repo, "requirements.txt")
        if reqs:
            for line in reqs.splitlines():
                line = line.split("#")[0].strip()
                if not line or line.startswith("-"):
                    continue
                m = re.match(r"([A-Za-z0-9_.\-\[\]]+)\s*(?:[=<>!~]+\s*(.+))?", line)
                if m:
                    self._dep(store, rid, m.group(1).split("[")[0], m.group(2) or "")

    def _dep(self, store: GraphStore, rid: str, name: str, version: str) -> None:
        d = Node(node_id(NodeType.DEPENDENCY, name), NodeType.DEPENDENCY, name, {})
        store.add_node(d)
        store.add_edge(Edge(rid, d.id, EdgeType.DEPENDS_ON, {"version": version}))

    def _ingest_workflows(self, owner: str, repo: str, rid: str, store: GraphStore) -> None:
        listing = self._get(f"/repos/{owner}/{repo}/contents/.github/workflows")
        if not isinstance(listing, list):
            return
        for f in listing:
            if not f["name"].endswith((".yml", ".yaml")):
                continue
            raw = self._file(owner, repo, f["path"])
            if not raw:
                continue
            pid = node_id(NodeType.PIPELINE, f"{owner}/{repo}/{f['name']}")
            store.add_node(Node(pid, NodeType.PIPELINE, f"{repo}/{f['name']}",
                                {"provider": "github-actions", "path": f["path"]}))
            store.add_edge(Edge(rid, pid, EdgeType.CONTAINS))
            try:
                wf = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                continue
            for job_name, job in (wf.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                sid = node_id(NodeType.PIPELINE_STEP, f"{owner}/{repo}/{f['name']}#{job_name}")
                steps_raw = yaml.dump(job)
                is_deploy = any(h in steps_raw.lower() for h in DEPLOY_HINTS)
                store.add_node(Node(sid, NodeType.PIPELINE_STEP, job_name,
                                    {"deploys": is_deploy,
                                     "runs_on": job.get("runs-on", "")}))
                store.add_edge(Edge(pid, sid, EdgeType.CONTAINS))
                for secret in set(SECRET_RE.findall(steps_raw)):
                    sec = Node(node_id(NodeType.SECRET, secret), NodeType.SECRET, secret,
                               {"stored_in": "github actions secret"})
                    store.add_node(sec)
                    store.add_edge(Edge(sid, sec.id, EdgeType.USES_SECRET))
