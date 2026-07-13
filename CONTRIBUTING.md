# Contributing to The Watcher

The codebase is deliberately small and the extension points are narrow. This guide covers the three things you're most likely to want to add: a detector, a connector, or a change to the demo company.

## Ground rules

- **Detectors are deterministic.** No LLM calls, no network, no randomness inside a detector. If two runs over the same graph disagree, that's a bug.
- **Every signal names its root node.** A detector that flags a resource without recording *which graph node structurally causes the problem* breaks the clustering model — that field is the whole product.
- **Every trace step must reference a real node.** `backend/tests/test_reasoning.py` enforces this; it will fail your PR if a trace mentions a node that isn't in the graph.

## Adding a detector

A detector is one generator function in [backend/watcher/reasoning/detectors.py](backend/watcher/reasoning/detectors.py) with this shape:

```python
def detect_my_pattern(store: GraphStore) -> Iterator[RawSignal]:
    """One line: what structural pattern this walks for."""
    for node in store.nodes(NodeType.SOMETHING):
        if not _looks_wrong(node):
            continue
        yield RawSignal(
            id=f"my_rule:{node.id}",          # stable — used for dedup across runs
            rule="my_rule",
            severity="high",                   # low | medium | high | critical
            resource=node.id,                  # the resource a scanner would flag
            root_node=cause.id,                # the node that structurally CAUSES it
            message="human-readable, one line, names the actual resources",
            evidence={...},                    # machine-readable proof
            trace=[
                ReasoningStep(cause.id, None, "why this node is the origin"),
                ReasoningStep(node.id, EdgeType.WHATEVER.value,
                              "how the problem reaches this resource"),
            ],
        )
```

Then:

1. Register it in `ALL_DETECTORS` at the bottom of the file.
2. Add a case to the demo company in [backend/watcher/ingest/demo.py](backend/watcher/ingest/demo.py) that triggers it — the demo is the living test fixture, and a detector nothing in the demo exercises is dead code.
3. Add a test in `backend/tests/test_reasoning.py`: build a minimal graph that triggers the signal, assert the root node and trace are what you expect, and build one that *almost* triggers it to pin down the boundary.

The distinction that matters most, worth restating: `resource` is what hurts, `root_node` is what to fix. For a wildcard-IAM finding the resource is the principal holding the permission; the root is the policy granting it. Clustering groups signals by root — get the root wrong and your detector's findings will smear across unrelated clusters.

### Severity guidance

- `critical` — exploitable from the internet today (public bucket with secrets, SSH open to 0.0.0.0/0 on a prod box)
- `high` — one compromised credential away (wildcard IAM, CI secrets crossing a trust boundary)
- `medium` — architectural debt with a plausible path to incident
- `low` — hygiene

## Adding a connector

Connectors live in [backend/watcher/ingest/](backend/watcher/ingest/) and their only job is to translate an external system into graph nodes and edges — no detection logic, ever. Look at `github_connector.py` for the pattern. Requirements:

- **Read-only.** The AWS connector ships with a minimum-permission policy ([docs/aws-readonly-policy.json](docs/aws-readonly-policy.json)); a new connector should document its equivalent.
- **Degrade loudly, not silently.** If you can't list a resource type, log it and continue — a partial graph with a warning beats a crash, but a silently partial graph produces confidently wrong findings.
- Emit node/edge types from [backend/watcher/graph/model.py](backend/watcher/graph/model.py). If the type you need doesn't exist, add it there first in its own commit — type additions affect every detector's assumptions.

## Changing the demo company

Brightpath (the demo org in `demo.py`) is deliberately broken in specific, documented ways — each flaw exists to exercise one detector and the case study walks through all of them. If you change it:

- Keep the finding counts in `README.md` and `docs/case-study.md` in sync (the "56 findings → 6 root causes" numbers are load-bearing in both).
- Every flaw gets a comment in `demo.py` saying which detector it feeds.

## Running the checks

```bash
cd backend
pip install -e ".[connectors,api,agent,dev]"
ruff check .
python -m pytest tests -v
```

CI runs exactly this plus a demo smoke test (`watcher ingest --demo && watcher report`), so if those pass locally you're green.

## Commit style

Small commits, present tense, say *why* when the diff doesn't. The history is part of the documentation.
