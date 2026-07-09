"""Graph data model for The Watcher.

Everything the system knows lives in one property graph. Nodes are the
things (repos, services, IAM roles, buckets...), edges are the trust and
call relationships between them. Keeping the vocabulary small and closed
on purpose: the reasoning layer pattern-matches over these types, and a
sprawling ontology makes those queries brittle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    REPOSITORY = "repository"
    SERVICE = "service"                # logical service, usually maps to a repo + runtime
    PIPELINE = "pipeline"              # a CI/CD workflow (e.g. one GitHub Actions file)
    PIPELINE_STEP = "pipeline_step"    # a job/step within a pipeline
    DEPENDENCY = "dependency"          # a third-party package
    IAM_ROLE = "iam_role"
    IAM_POLICY = "iam_policy"
    S3_BUCKET = "s3_bucket"
    SECURITY_GROUP = "security_group"
    LAMBDA_FUNCTION = "lambda_function"
    SECRET = "secret"                  # a credential/secret reference (not the value!)
    EXTERNAL = "external"              # the internet / third-party endpoints


class EdgeType(str, Enum):
    # structure
    CONTAINS = "contains"              # repo -> pipeline, pipeline -> step
    DEPLOYS = "deploys"                # pipeline/step -> service or lambda
    IMPLEMENTS = "implements"          # repo -> service
    DEPENDS_ON = "depends_on"          # repo -> dependency, service -> service
    # trust / permission
    ASSUMES = "assumes"                # service/lambda/step -> iam_role
    ATTACHED_TO = "attached_to"        # iam_policy -> iam_role
    GRANTS_ACCESS = "grants_access"    # iam_policy -> resource (bucket, lambda, ...)
    GUARDED_BY = "guarded_by"          # service/lambda -> security_group
    ALLOWS_TRAFFIC = "allows_traffic"  # security_group -> security_group / external
    # data & secrets
    READS = "reads"                    # service -> bucket etc.
    WRITES = "writes"
    USES_SECRET = "uses_secret"        # service/step -> secret
    EXPOSED_TO = "exposed_to"          # resource -> external (public exposure)
    CALLS = "calls"                    # service -> service (runtime call)


@dataclass
class Node:
    id: str                            # globally unique, e.g. "iam_role:payments-lambda-exec"
    type: NodeType
    name: str
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type.value, "name": self.name, "props": self.props}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        return cls(id=d["id"], type=NodeType(d["type"]), name=d["name"], props=d.get("props", {}))


@dataclass
class Edge:
    src: str
    dst: str
    type: EdgeType
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "type": self.type.value, "props": self.props}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Edge":
        return cls(src=d["src"], dst=d["dst"], type=EdgeType(d["type"]), props=d.get("props", {}))


def node_id(ntype: NodeType, name: str) -> str:
    """Stable id scheme so re-ingestion is idempotent."""
    return f"{ntype.value}:{name}"
