"""LLM pass: clustering review + narrative generation via Claude.

Division of labour, and I want to be precise about it because "AI-powered
security tool" usually means vibes:

  - Detectors (deterministic) decide WHAT is wrong. The LLM cannot add,
    remove, or re-score findings.
  - The LLM writes the narrative ("how we got here") and can propose
    MERGING clusters it recognizes as the same underlying cause. Merges
    are validated: both clusters must share graph structure or the merge
    is rejected.

Degrades gracefully: no ANTHROPIC_API_KEY -> template narratives, fully
offline. The demo must never depend on somebody's API quota.
"""

from __future__ import annotations

import json
import os
from typing import Any

MODEL = os.environ.get("WATCHER_MODEL", "claude-sonnet-5")

SYSTEM = """You are a principal security architect reviewing structural findings \
from a graph analysis of a company's code, CI/CD and AWS estate. You write like \
a person explaining to a colleague, not like a report generator. No headers, no \
bullet lists, no 'it is important to note'. Be specific to the evidence given."""

NARRATIVE_PROMPT = """Here is one clustered root-cause finding as JSON (the raw \
signals it explains, the graph reasoning trace, and the blast radius estimate):

{finding}

Write a short "how we got here" narrative (4-7 sentences, one paragraph) telling \
the story of this root cause: how this kind of thing typically comes to exist, \
what it means concretely for THIS system given the evidence, and why fixing the \
root beats patching the symptoms. Ground every claim in the provided evidence - \
if the evidence says the policy comes from a copied terraform module, use that. \
Return only the paragraph."""


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def narrate(finding_dict: dict[str, Any]) -> str | None:
    """Ask Claude for the narrative paragraph. Returns None on any failure -
    caller falls back to the template."""
    if not available():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        # keep the payload small: signals can be numerous but repetitive
        slim = dict(finding_dict)
        slim["signals"] = slim["signals"][:6] + (
            [{"note": f"... and {len(finding_dict['signals']) - 6} more of the same shape"}]
            if len(finding_dict["signals"]) > 6 else [])
        msg = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=SYSTEM,
            messages=[{"role": "user",
                       "content": NARRATIVE_PROMPT.format(finding=json.dumps(slim, indent=1))}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
        print(f"  llm narrative failed ({type(exc).__name__}), using template")
        return None


def template_narrative(finding_dict: dict[str, Any]) -> str:
    """Offline fallback. Honest but generic - the LLM version is better,
    and the dashboard labels which one you're seeing."""
    br = finding_dict["blast_radius"]
    return (
        f"{finding_dict['description']} "
        f"This single root cause explains {finding_dict['signal_count']} findings that "
        f"a conventional scanner would report separately. "
        f"Fixing it touches {len(br['services_touched'])} services "
        f"(estimated effort: {br['effort']}) - {br['effort_detail']}. "
        f"Main risk while fixing: {br['breakage_risk']}."
    )
