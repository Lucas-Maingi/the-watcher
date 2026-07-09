from watcher.graph import Edge, EdgeType, GraphStore, Node, NodeType, node_id


def build_tiny_graph() -> GraphStore:
    s = GraphStore()
    role = Node(node_id(NodeType.IAM_ROLE, "api-exec"), NodeType.IAM_ROLE, "api-exec")
    policy = Node(node_id(NodeType.IAM_POLICY, "god-mode"), NodeType.IAM_POLICY, "god-mode",
                  {"actions": ["*"], "resources": ["*"]})
    fn = Node(node_id(NodeType.LAMBDA_FUNCTION, "api"), NodeType.LAMBDA_FUNCTION, "api")
    bucket = Node(node_id(NodeType.S3_BUCKET, "payments-data"), NodeType.S3_BUCKET, "payments-data")
    for n in (role, policy, fn, bucket):
        s.add_node(n)
    s.add_edge(Edge(fn.id, role.id, EdgeType.ASSUMES))
    s.add_edge(Edge(policy.id, role.id, EdgeType.ATTACHED_TO))
    s.add_edge(Edge(policy.id, bucket.id, EdgeType.GRANTS_ACCESS))
    return s


def test_idempotent_ingestion():
    s = build_tiny_graph()
    before = s.summary()
    # ingest the same thing twice, graph shouldn't grow
    s.add_node(Node(node_id(NodeType.IAM_ROLE, "api-exec"), NodeType.IAM_ROLE, "api-exec",
                    {"arn": "arn:aws:iam::123:role/api-exec"}))
    s.add_edge(Edge(node_id(NodeType.LAMBDA_FUNCTION, "api"),
                    node_id(NodeType.IAM_ROLE, "api-exec"), EdgeType.ASSUMES))
    after = s.summary()
    assert before["nodes"] == after["nodes"]
    assert before["edges"] == after["edges"]
    # but props got merged in
    assert s.get_node(node_id(NodeType.IAM_ROLE, "api-exec")).props["arn"].endswith("api-exec")


def test_traversal_and_roundtrip(tmp_path):
    s = build_tiny_graph()
    fn = node_id(NodeType.LAMBDA_FUNCTION, "api")
    reach = s.reachable_from(fn, via={EdgeType.ASSUMES})
    assert node_id(NodeType.IAM_ROLE, "api-exec") in reach

    p = tmp_path / "graph.json"
    s.save(p)
    s2 = GraphStore.load(p)
    assert s2.summary() == s.summary()
    assert s2.get_node(node_id(NodeType.IAM_POLICY, "god-mode")).props["actions"] == ["*"]
