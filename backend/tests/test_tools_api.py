"""Tests for the agent tool surface and the HTTP API on top of it."""

import pytest
from fastapi.testclient import TestClient

from watcher import tools
from watcher.api.main import app
from watcher.ingest.demo import generate


@pytest.fixture(autouse=True)
def demo_graph(tmp_path, monkeypatch):
    p = tmp_path / "graph.json"
    generate().save(p)
    monkeypatch.setattr(tools, "DEFAULT_GRAPH", p)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tools.reset_cache()
    yield
    tools.reset_cache()


def test_get_root_causes_and_severity_filter():
    all_f = tools.get_root_causes()
    crit = tools.get_root_causes(severity="critical")
    assert 0 < len(crit) < len(all_f)
    assert all(f["severity"] == "critical" for f in crit)


def test_explain_finding_roundtrip():
    fid = tools.get_root_causes()[0]["id"]
    detail = tools.explain_finding(fid)
    assert detail["id"] == fid
    assert detail["trace"] and detail["narrative"] and detail["compliance"]


def test_context_for_file_path():
    """The agent use case: 'what affects the file I'm editing'."""
    ctx = tools.get_context_for("services/payments-service/src/handler.py")
    assert ctx["service"] == "payments-service"
    titles = " ".join(rc["title"] for rc in ctx["root_causes"])
    # payments-service is a lambda on the shared exec role AND deploys
    # via the long-lived ci key - both must show up
    assert "IAM policy" in titles
    assert "long-lived" in titles


def test_context_for_unknown_is_helpful():
    ctx = tools.get_context_for("no-such-thing")
    assert "error" in ctx and ctx["known_services"]


def test_http_api_end_to_end():
    client = TestClient(app)
    summary = client.get("/api/summary").json()
    assert summary["root_causes"] < summary["raw_findings"]

    listing = client.get("/api/root-causes").json()
    fid = listing[0]["id"]
    detail = client.get(f"/api/root-causes/{fid}").json()
    assert detail["signals"]
    br = client.get(f"/api/root-causes/{fid}/blast-radius").json()
    assert br["effort"] in ("hours", "days", "weeks")
    assert client.get("/api/root-causes/rc_nope").status_code == 404
