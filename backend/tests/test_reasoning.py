"""Reasoning engine tests against the demo dataset. These pin down the
core product claim: N raw signals collapse into a small number of root
causes, and every reasoning trace refers to real graph elements."""

import pytest

from watcher.ingest.demo import generate
from watcher.reasoning import ReasoningEngine


@pytest.fixture(scope="module")
def engine() -> ReasoningEngine:
    return ReasoningEngine(generate(), use_llm=False)


def test_signals_collapse_into_few_root_causes(engine):
    signals = engine.raw_signals()
    findings = engine.root_causes()
    assert len(signals) >= 30, "demo should look noisy in scanner view"
    assert len(findings) <= 8, "root cause view should be readable in one screen"
    # every signal is explained by exactly one root cause
    explained = [s.id for f in findings for s in f.signals]
    assert sorted(explained) == sorted(s.id for s in signals)


def test_the_flagship_cluster(engine):
    """The shared lambda-exec policy: 12 lambdas, one root cause."""
    findings = engine.root_causes()
    iam = [f for f in findings if f.root_node == "iam_policy:lambda-exec-standard"]
    assert len(iam) == 1
    f = iam[0]
    assert f.signal_count == 12
    assert f.severity == "high"
    assert len(f.blast_radius.services_touched) == 12
    assert f.blast_radius.effort in ("days", "weeks")


def test_traces_only_reference_real_graph_elements(engine):
    """The anti-black-box guarantee: every node in every reasoning step
    must exist in the graph. If this fails, the 'why' view is lying."""
    store = engine.store
    for f in engine.root_causes():
        assert f.trace, f"{f.id} has no reasoning trace"
        for step in f.trace:
            assert store.get_node(step.node) is not None, \
                f"trace in {f.id} references nonexistent node {step.node}"


def test_findings_are_ranked_sanely(engine):
    findings = engine.root_causes()
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranks = [sev_rank[f.severity] for f in findings]
    assert ranks == sorted(ranks)
    # the public pii bucket should be at/near the top
    assert findings[0].severity == "critical"


def test_narratives_exist_without_llm(engine):
    for f in engine.root_causes():
        assert len(f.narrative) > 100, "template narrative should still say something real"
