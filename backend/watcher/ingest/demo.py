"""Demo dataset: "Brightpath", a fake mid-size fintech.

~20 services with architecture problems I've genuinely seen in the wild,
planted deliberately so the reasoning engine has real root causes to find:

  1. One shared "lambda-exec-standard" IAM policy (s3:*, dynamodb:*, sqs:*
     on Resource:*) attached to a role that a dozen Lambdas assume. This is
     THE demo case: a scanner reports it as 12+ separate findings; the
     actual problem is one copy-pasted Terraform module.
  2. A "temporary" security group opening 22 and 5432 to 0.0.0.0/0,
     shared by several services because someone reused the sg id.
  3. A public S3 bucket that two services write customer exports into.
  4. Long-lived AWS keys stored as GitHub Actions secrets and used by
     deploy steps in most repos (instead of OIDC) - secrets crossing the
     CI trust boundary everywhere.
  5. platform-core: a service everything calls and one team owns. Single
     point of failure and the widest blast radius in the company.

Everything is generated deterministically (no randomness) so screenshots,
tests and demos never drift.
"""

from __future__ import annotations

from ..graph import Edge, EdgeType, GraphStore, Node, NodeType, node_id


# (service, team, language, calls)
SERVICES: list[tuple[str, str, str, list[str]]] = [
    ("platform-core",     "platform", "go",     []),
    ("auth-service",      "platform", "go",     ["platform-core"]),
    ("api-gateway",       "platform", "node",   ["auth-service", "platform-core"]),
    ("payments-service",  "payments", "python", ["platform-core", "ledger-service"]),
    ("ledger-service",    "payments", "python", ["platform-core"]),
    ("payouts-service",   "payments", "python", ["ledger-service", "platform-core"]),
    ("card-issuing",      "payments", "python", ["platform-core", "kyc-service"]),
    ("kyc-service",       "risk",     "python", ["platform-core"]),
    ("fraud-scoring",     "risk",     "python", ["platform-core", "kyc-service"]),
    ("risk-rules",        "risk",     "python", ["fraud-scoring"]),
    ("notifications",     "growth",   "node",   ["platform-core"]),
    ("email-renderer",    "growth",   "node",   ["notifications"]),
    ("referrals",         "growth",   "node",   ["platform-core", "notifications"]),
    ("analytics-etl",     "data",     "python", ["platform-core"]),
    ("reporting-api",     "data",     "python", ["analytics-etl", "platform-core"]),
    ("data-export",       "data",     "python", ["analytics-etl"]),
    ("customer-portal",   "web",      "node",   ["api-gateway"]),
    ("admin-console",     "web",      "node",   ["api-gateway", "reporting-api"]),
    ("webhooks-ingest",   "platform", "go",     ["platform-core"]),
    ("mobile-bff",        "web",      "node",   ["api-gateway"]),
]

# services that run as lambdas and all assume the same over-permissioned role
LAMBDA_SERVICES = [
    "payments-service", "ledger-service", "payouts-service", "card-issuing",
    "kyc-service", "fraud-scoring", "risk-rules", "notifications",
    "email-renderer", "referrals", "analytics-etl", "data-export",
]

# services that got the "temporary" wide-open security group
LOOSE_SG_SERVICES = ["reporting-api", "admin-console", "webhooks-ingest", "analytics-etl"]

# repos whose deploy pipelines use long-lived AWS keys instead of OIDC
LEGACY_CI_AUTH = [s for s, _, _, _ in SERVICES if s not in ("customer-portal", "mobile-bff")]


def generate(store: GraphStore | None = None) -> GraphStore:
    s = store or GraphStore()
    _external = Node(node_id(NodeType.EXTERNAL, "internet"), NodeType.EXTERNAL, "internet")
    s.add_node(_external)

    # --- the shared over-permissioned lambda policy (root cause #1) ---
    exec_policy = Node(
        node_id(NodeType.IAM_POLICY, "lambda-exec-standard"),
        NodeType.IAM_POLICY, "lambda-exec-standard",
        {
            "actions": ["s3:*", "dynamodb:*", "sqs:*", "logs:*"],
            "resources": ["*"],
            "managed": False,
            "source": "terraform module: modules/lambda-service (copied since 2023)",
        },
    )
    exec_role = Node(
        node_id(NodeType.IAM_ROLE, "lambda-exec-standard-role"),
        NodeType.IAM_ROLE, "lambda-exec-standard-role",
        {"trust": "lambda.amazonaws.com"},
    )
    s.add_node(exec_policy)
    s.add_node(exec_role)
    s.add_edge(Edge(exec_policy.id, exec_role.id, EdgeType.ATTACHED_TO))

    # --- the "temporary" wide-open security group (root cause #2) ---
    loose_sg = Node(
        node_id(NodeType.SECURITY_GROUP, "sg-debug-temp"),
        NodeType.SECURITY_GROUP, "sg-debug-temp",
        {"rules": [
            {"port": 22, "cidr": "0.0.0.0/0", "protocol": "tcp"},
            {"port": 5432, "cidr": "0.0.0.0/0", "protocol": "tcp"},
        ], "description": "TEMP: debugging prod incident 2024-03 (never removed)"},
    )
    s.add_node(loose_sg)
    s.add_edge(Edge(loose_sg.id, _external.id, EdgeType.ALLOWS_TRAFFIC,
                    {"ports": [22, 5432], "cidr": "0.0.0.0/0"}))

    # --- the public exports bucket (root cause #3) ---
    public_bucket = Node(
        node_id(NodeType.S3_BUCKET, "brightpath-customer-exports"),
        NodeType.S3_BUCKET, "brightpath-customer-exports",
        {"public": True, "policy": "AllowPublicRead", "contains_pii": True},
    )
    s.add_node(public_bucket)
    s.add_edge(Edge(public_bucket.id, _external.id, EdgeType.EXPOSED_TO,
                    {"via": "bucket policy Principal:*"}))

    # --- the long-lived CI credentials secret (root cause #4) ---
    ci_secret = Node(
        node_id(NodeType.SECRET, "AWS_DEPLOY_KEY"),
        NodeType.SECRET, "AWS_DEPLOY_KEY",
        {"kind": "long-lived aws access key", "stored_in": "github actions org secret",
         "rotated": "2024-01 (18 months ago)"},
    )
    s.add_node(ci_secret)
    deploy_role = Node(
        node_id(NodeType.IAM_ROLE, "ci-deploy-admin"),
        NodeType.IAM_ROLE, "ci-deploy-admin",
        {"trust": "iam user brightpath-ci (access key)"},
    )
    admin_policy = Node(
        node_id(NodeType.IAM_POLICY, "AdministratorAccess"),
        NodeType.IAM_POLICY, "AdministratorAccess",
        {"actions": ["*"], "resources": ["*"], "managed": True},
    )
    s.add_node(deploy_role)
    s.add_node(admin_policy)
    s.add_edge(Edge(admin_policy.id, deploy_role.id, EdgeType.ATTACHED_TO))

    # per-team buckets and a couple of scoped roles done *right*, so the
    # graph isn't a caricature - good patterns exist alongside the bad
    for team in ("payments", "risk", "data"):
        b = Node(node_id(NodeType.S3_BUCKET, f"brightpath-{team}-data"),
                 NodeType.S3_BUCKET, f"brightpath-{team}-data",
                 {"public": False, "encrypted": True})
        s.add_node(b)

    good_sg = Node(node_id(NodeType.SECURITY_GROUP, "sg-internal-only"),
                   NodeType.SECURITY_GROUP, "sg-internal-only",
                   {"rules": [{"port": 443, "cidr": "10.0.0.0/8", "protocol": "tcp"}]})
    s.add_node(good_sg)

    for name, team, lang, calls in SERVICES:
        repo = Node(node_id(NodeType.REPOSITORY, name), NodeType.REPOSITORY, name,
                    {"language": lang, "team": team, "default_branch": "main"})
        svc = Node(node_id(NodeType.SERVICE, name), NodeType.SERVICE, name,
                   {"team": team, "runtime": "lambda" if name in LAMBDA_SERVICES else "ecs"})
        s.add_node(repo)
        s.add_node(svc)
        s.add_edge(Edge(repo.id, svc.id, EdgeType.IMPLEMENTS))

        # CI pipeline per repo
        pipe = Node(node_id(NodeType.PIPELINE, f"{name}/deploy.yml"),
                    NodeType.PIPELINE, f"{name}/deploy.yml", {"provider": "github-actions"})
        step = Node(node_id(NodeType.PIPELINE_STEP, f"{name}/deploy.yml#deploy"),
                    NodeType.PIPELINE_STEP, "deploy", {"uses": "aws-actions/configure-aws-credentials"})
        s.add_node(pipe)
        s.add_node(step)
        s.add_edge(Edge(repo.id, pipe.id, EdgeType.CONTAINS))
        s.add_edge(Edge(pipe.id, step.id, EdgeType.CONTAINS))
        s.add_edge(Edge(step.id, svc.id, EdgeType.DEPLOYS))

        if name in LEGACY_CI_AUTH:
            s.add_edge(Edge(step.id, ci_secret.id, EdgeType.USES_SECRET))
            s.add_edge(Edge(step.id, deploy_role.id, EdgeType.ASSUMES,
                            {"via": "long-lived access key"}))

        # runtime identity
        if name in LAMBDA_SERVICES:
            fn = Node(node_id(NodeType.LAMBDA_FUNCTION, name), NodeType.LAMBDA_FUNCTION, name,
                      {"runtime": "python3.12" if lang == "python" else "nodejs20.x"})
            s.add_node(fn)
            s.add_edge(Edge(svc.id, fn.id, EdgeType.DEPENDS_ON, {"is": "runtime"}))
            s.add_edge(Edge(fn.id, exec_role.id, EdgeType.ASSUMES))
        else:
            # scoped per-service role, done properly
            r = Node(node_id(NodeType.IAM_ROLE, f"{name}-task-role"), NodeType.IAM_ROLE,
                     f"{name}-task-role", {"trust": "ecs-tasks.amazonaws.com"})
            p = Node(node_id(NodeType.IAM_POLICY, f"{name}-scoped"), NodeType.IAM_POLICY,
                     f"{name}-scoped",
                     {"actions": ["s3:GetObject", "sqs:SendMessage"],
                      "resources": [f"arn:aws:s3:::brightpath-{team}-data/*"]})
            s.add_node(r)
            s.add_node(p)
            s.add_edge(Edge(p.id, r.id, EdgeType.ATTACHED_TO))
            s.add_edge(Edge(svc.id, r.id, EdgeType.ASSUMES))

        # network placement
        sg = loose_sg if name in LOOSE_SG_SERVICES else good_sg
        s.add_edge(Edge(svc.id, sg.id, EdgeType.GUARDED_BY))

        # data access
        team_bucket = node_id(NodeType.S3_BUCKET, f"brightpath-{team}-data")
        if s.get_node(team_bucket):
            s.add_edge(Edge(svc.id, team_bucket, EdgeType.READS))
            s.add_edge(Edge(svc.id, team_bucket, EdgeType.WRITES))

        for callee in calls:
            s.add_edge(Edge(svc.id, node_id(NodeType.SERVICE, callee), EdgeType.CALLS))

    # the two services dumping customer data into the public bucket
    for name in ("data-export", "reporting-api"):
        s.add_edge(Edge(node_id(NodeType.SERVICE, name), public_bucket.id, EdgeType.WRITES,
                        {"data": "customer export csv (pii)"}))

    # shared dependencies so the dependency axis isn't empty
    for dep, ver, repos in [
        ("requests", "2.31.0", [n for n, _, l, _ in SERVICES if l == "python"]),
        ("express", "4.18.2", [n for n, _, l, _ in SERVICES if l == "node"]),
        ("internal-sdk", "0.9.4", [n for n, _, _, _ in SERVICES]),
    ]:
        d = Node(node_id(NodeType.DEPENDENCY, dep), NodeType.DEPENDENCY, dep, {"version": ver})
        s.add_node(d)
        for rname in repos:
            s.add_edge(Edge(node_id(NodeType.REPOSITORY, rname), d.id, EdgeType.DEPENDS_ON,
                            {"version": ver}))

    return s
