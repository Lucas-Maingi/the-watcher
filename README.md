# The Watcher

Architectural security intelligence. Instead of dumping 200 scanner alerts on you, The Watcher builds a structural graph of your stack — repos, CI pipelines, IAM roles, buckets, security groups, the trust relationships between all of them — and reasons over it to find the handful of *architectural root causes* actually generating those alerts.

The pitch in one line: a single over-permissioned IAM pattern copy-pasted across 40 services produces 40+ scanner findings. Fix the pattern once, all 40 go away. Every tool I've used shows me the 40. Nobody shows me the one.

## What it does (or will do — see status below)

1. **Ingests** your architecture into a property graph: GitHub repos, Actions workflows, dependency manifests, AWS IAM roles/policies, S3 buckets, security groups, Lambda configs.
2. **Reasons** over the graph: deterministic queries surface candidate structural patterns (shared wide policies, secrets crossing trust boundaries, single points of failure), then an LLM pass clusters and explains them as root causes — with the full reasoning trace exposed, not a black-box score.
3. **Recommends** with blast radius attached: what fixing this touches, which services, roughly how much effort, what might break.
4. **Talks to agents**: the reasoning engine is exposed as tools (MCP-friendly) so a coding agent can ask "what architectural issues affect the file I'm editing" and get root-cause context, not alert noise.

## Why NetworkX and not Neo4j

I started sketching this against Neo4j and stopped. For a graph of a few thousand nodes, running a JVM database in Docker buys me nothing except a slower dev loop and one more thing that can be broken during a live demo. NetworkX in-process with JSON snapshots is plenty at this scale, the query code is plain Python I can debug with a print statement, and the whole thing runs with zero services. If this ever needs to hold a real enterprise estate, the graph store is behind one interface (`watcher/graph/store.py`) and swapping it is a contained job.

## Status

- [ ] Phase 1 — graph model, GitHub + AWS connectors, demo dataset generator
- [ ] Phase 2 — reasoning engine (the actual point of this project)
- [ ] Phase 3 — dashboard, agent tool interface, compliance mapping
- [ ] Phase 4 — landing page, case study walkthrough

I'll keep this honest as I go — things that are stubbed will say so.

## Quick start

Coming with Phase 1. The goal: `docker compose up`, or just `pip install -e backend && watcher ingest --demo`, and you have a queryable graph of a realistic fake company with deliberately bad architecture.
