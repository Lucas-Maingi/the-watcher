"""AWS connector. Strictly read-only - every call here is a Describe/List/Get.

Meant to run under a scoped role; the minimum policy it needs is in
docs/aws-readonly-policy.json. Covers the phase-1 resource set: IAM
roles/policies, security groups, S3 buckets (policy + public access
block), and Lambda functions with their role bindings.

I have not run this against a large production account. Pagination is
handled, throttling/backoff beyond boto3's defaults is not. Known
simplification: only *attached* customer-managed policies and inline
role policies are modelled; permission boundaries and SCPs are out of
scope for now and honestly might stay there.
"""

from __future__ import annotations

import json
from typing import Any

import boto3

from ..graph import Edge, EdgeType, GraphStore, Node, NodeType, node_id


def _doc(policy_doc: Any) -> dict:
    if isinstance(policy_doc, str):
        return json.loads(policy_doc)
    return policy_doc or {}


def _summarize_statements(doc: dict) -> tuple[list[str], list[str]]:
    """Flatten a policy document into (actions, resources) for the graph."""
    actions: list[str] = []
    resources: list[str] = []
    stmts = doc.get("Statement", [])
    if isinstance(stmts, dict):
        stmts = [stmts]
    for st in stmts:
        if st.get("Effect") != "Allow":
            continue
        a = st.get("Action", [])
        r = st.get("Resource", [])
        actions += [a] if isinstance(a, str) else list(a)
        resources += [r] if isinstance(r, str) else list(r)
    return sorted(set(actions)), sorted(set(resources))


class AWSConnector:
    def __init__(self, profile: str | None = None, region: str | None = None) -> None:
        self.session = boto3.Session(profile_name=profile, region_name=region)

    def ingest(self, store: GraphStore) -> None:
        external = Node(node_id(NodeType.EXTERNAL, "internet"), NodeType.EXTERNAL, "internet")
        store.add_node(external)
        print("  iam ...")
        self._ingest_iam(store)
        print("  security groups ...")
        self._ingest_security_groups(store, external.id)
        print("  s3 ...")
        self._ingest_s3(store, external.id)
        print("  lambda ...")
        self._ingest_lambda(store)

    # ---------------- IAM ----------------

    def _ingest_iam(self, store: GraphStore) -> None:
        iam = self.session.client("iam")
        for page in iam.get_paginator("list_roles").paginate():
            for role in page["Roles"]:
                rid = node_id(NodeType.IAM_ROLE, role["RoleName"])
                trust = json.dumps(role.get("AssumeRolePolicyDocument", {}))
                store.add_node(Node(rid, NodeType.IAM_ROLE, role["RoleName"],
                                    {"arn": role["Arn"], "trust": trust}))
                # attached managed policies
                for ap in iam.get_paginator("list_attached_role_policies") \
                             .paginate(RoleName=role["RoleName"]):
                    for pol in ap["AttachedPolicies"]:
                        pid = node_id(NodeType.IAM_POLICY, pol["PolicyName"])
                        props = {"arn": pol["PolicyArn"],
                                 "managed": pol["PolicyArn"].startswith("arn:aws:iam::aws:")}
                        try:
                            v = iam.get_policy(PolicyArn=pol["PolicyArn"])["Policy"]
                            doc = iam.get_policy_version(
                                PolicyArn=pol["PolicyArn"],
                                VersionId=v["DefaultVersionId"])["PolicyVersion"]["Document"]
                            props["actions"], props["resources"] = _summarize_statements(_doc(doc))
                        except Exception:
                            pass  # aws-managed policy docs can be denied; keep the node anyway
                        store.add_node(Node(pid, NodeType.IAM_POLICY, pol["PolicyName"], props))
                        store.add_edge(Edge(pid, rid, EdgeType.ATTACHED_TO))
                # inline policies
                for ip in iam.get_paginator("list_role_policies") \
                             .paginate(RoleName=role["RoleName"]):
                    for pname in ip["PolicyNames"]:
                        doc = _doc(iam.get_role_policy(RoleName=role["RoleName"],
                                                       PolicyName=pname)["PolicyDocument"])
                        actions, resources = _summarize_statements(doc)
                        pid = node_id(NodeType.IAM_POLICY, f"{role['RoleName']}/{pname}")
                        store.add_node(Node(pid, NodeType.IAM_POLICY, pname,
                                            {"inline": True, "actions": actions,
                                             "resources": resources}))
                        store.add_edge(Edge(pid, rid, EdgeType.ATTACHED_TO))

    # ---------------- EC2 security groups ----------------

    def _ingest_security_groups(self, store: GraphStore, external_id: str) -> None:
        ec2 = self.session.client("ec2")
        for page in ec2.get_paginator("describe_security_groups").paginate():
            for sg in page["SecurityGroups"]:
                sgid = node_id(NodeType.SECURITY_GROUP, sg["GroupId"])
                rules = []
                open_ports = []
                for perm in sg.get("IpPermissions", []):
                    port = perm.get("FromPort", 0)
                    for rng in perm.get("IpRanges", []):
                        cidr = rng.get("CidrIp", "")
                        rules.append({"port": port, "cidr": cidr,
                                      "protocol": perm.get("IpProtocol", "tcp")})
                        if cidr == "0.0.0.0/0":
                            open_ports.append(port)
                store.add_node(Node(sgid, NodeType.SECURITY_GROUP,
                                    sg.get("GroupName", sg["GroupId"]),
                                    {"rules": rules, "description": sg.get("Description", "")}))
                if open_ports:
                    store.add_edge(Edge(sgid, external_id, EdgeType.ALLOWS_TRAFFIC,
                                        {"ports": sorted(set(open_ports)), "cidr": "0.0.0.0/0"}))

    # ---------------- S3 ----------------

    def _ingest_s3(self, store: GraphStore, external_id: str) -> None:
        s3 = self.session.client("s3")
        for b in s3.list_buckets().get("Buckets", []):
            name = b["Name"]
            bid = node_id(NodeType.S3_BUCKET, name)
            props: dict[str, Any] = {"public": False}
            try:
                pab = s3.get_public_access_block(Bucket=name) \
                        ["PublicAccessBlockConfiguration"]
                fully_blocked = all(pab.values())
            except Exception:
                fully_blocked = False
            try:
                pol = json.loads(s3.get_bucket_policy(Bucket=name)["Policy"])
                props["policy"] = pol
                stmts = pol.get("Statement", [])
                if isinstance(stmts, dict):
                    stmts = [stmts]
                has_public_stmt = any(
                    st.get("Effect") == "Allow" and st.get("Principal") in ("*", {"AWS": "*"})
                    for st in stmts)
            except Exception:
                has_public_stmt = False
            props["public"] = has_public_stmt and not fully_blocked
            store.add_node(Node(bid, NodeType.S3_BUCKET, name, props))
            if props["public"]:
                store.add_edge(Edge(bid, external_id, EdgeType.EXPOSED_TO,
                                    {"via": "bucket policy Principal:*"}))

    # ---------------- Lambda ----------------

    def _ingest_lambda(self, store: GraphStore) -> None:
        lam = self.session.client("lambda")
        for page in lam.get_paginator("list_functions").paginate():
            for fn in page["Functions"]:
                fid = node_id(NodeType.LAMBDA_FUNCTION, fn["FunctionName"])
                store.add_node(Node(fid, NodeType.LAMBDA_FUNCTION, fn["FunctionName"],
                                    {"runtime": fn.get("Runtime", ""),
                                     "arn": fn["FunctionArn"]}))
                role_arn = fn.get("Role", "")
                if role_arn:
                    role_name = role_arn.split("/")[-1]
                    rid = node_id(NodeType.IAM_ROLE, role_name)
                    store.add_node(Node(rid, NodeType.IAM_ROLE, role_name, {"arn": role_arn}))
                    store.add_edge(Edge(fid, rid, EdgeType.ASSUMES))
