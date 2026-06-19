# Agentic OS

**The Agentic Operating System** is a temporal knowledge graph that makes AI agents
actually useful inside a company — by giving them knowledge that is freshness-scored,
authority-weighted, and permission-aware.

Standard RAG retrieves the most *semantically similar* document. Agentic OS retrieves
the most *trustworthy, current, and authorized* one. Those are different problems.

---

## The problem with plain RAG

When you point an agent at your company's knowledge base, it retrieves documents that
are semantically close to the query. But it has no idea whether the answer is from a
merged PR merged yesterday or an abandoned RFC from 2021. It cannot tell whether a
Slack message carries the same weight as an Architecture Decision Record. And it
has no concept of whether the querying agent is *allowed* to see the result.

Agents built on plain RAG hallucinate less but **confidently cite stale, low-authority,
or unauthorized information**. That is worse in production than no agent at all.

---

## How Agentic OS fixes this

Every piece of knowledge becomes an `Artifact` with three signals plain RAG lacks:

### 1. Temperature (freshness decay)
Knowledge cools over time using a thermodynamic model:

```
T(t) = T_ambient + (T(t-1) - T_ambient) × exp(−k × Δt)
```

A merged PR from this morning starts at `T = 1.0`. A wiki page from two years ago
may have decayed to `T = 0.12`. Temperature multiplies directly into the retrieval
score — cold knowledge ranks lower automatically.

### 2. Authority scoring
The *source* of knowledge signals its trust level, set at ingestion time:

| Source | Authority |
|--------|-----------|
| Architecture Decision Record | 0.95 |
| Runbook / playbook | 0.90 |
| Merged pull request | 0.85 |
| README | 0.85 |
| API documentation | 0.80 |
| Open issue | 0.70 |
| Slack message | 0.40 |

A Slack message that contradicts a merged PR loses — by design.

### 3. Permission-coherence (hard ACL gate)
Every artifact carries `allowed_users` and `allowed_groups` from the moment it is
ingested. At query time, `Access(user, artifact)` is a **binary gate** that zeroes
the score entirely before any other factor is applied. An agent can never surface
knowledge its authorizing human could not see.

### Retrieval formula

```
Score(q, i) = Access(user, i) × Sim(q, xᵢ) × Freshness(i) × Authority(i) × Usage(i) × GraphBoost(i)
```

`Access` is the outermost term — a zero there makes the rest irrelevant.

---

## Architecture

```
Sources          Connectors       Events        Ingestion         Storage
──────────       ──────────       ──────        ─────────         ───────
GitHub PRs  ──►  github.py   ──►
GitHub Issues──►                  Event  ──►  IngestionService ──► ChromaDB
Markdown .md──►  markdown.py ──►  (unified      (embed, score,     (vectors +
Slack (soon)──►  slack.py    ──►   schema)        dedup, upsert)    metadata)
                                                      │
                                               Freshness decay
                                               (asyncio loop,
                                                every 60s dev /
                                                hourly prod)
                                                      │
                                              /query endpoint
                                          (ACL → semantic → score → rerank)
                                                      │
                                              JSON response with
                                              citations + confidence
```

**Stack:** Python 3.13 · FastAPI · ChromaDB · sentence-transformers (local, no API key) · Neo4j (Day 3) · React + Vite (Day 3) · Render (backend) · Vercel (frontend)

---

## Running locally

### Prerequisites
- Python 3.13
- A GitHub Personal Access Token (optional — public repos work without one)

### Setup

```bash
git clone https://github.com/Tanay126/agentic-os
cd agentic-os/backend

python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
GITHUB_TOKEN=ghp_...        # optional for public repos
ANTHROPIC_API_KEY=sk-ant-...  # needed for Day 3+ agent features
DATA_DIR=./data
DECAY_INTERVAL_SECONDS=60   # freshness decay cadence (seconds)
```

### Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

### Ingest knowledge

```bash
# Pull from a GitHub repo (PRs + Issues)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"owner": "your-org", "repo": "your-repo", "limit": 100}'

# Ingest local markdown docs
curl -X POST http://localhost:8000/ingest/markdown \
  -H "Content-Type: application/json" \
  -d '{"directory_path": "/path/to/your/docs"}'
```

### Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how do we handle auth token expiry?",
    "user_id": "alice",
    "groups": ["engineering", "backend"],
    "n_results": 5
  }'
```

Response includes per-result `freshness_warning` (fires when temperature < 0.5)
and `contradiction_alert` (Day 3), so the consumer always knows how much to trust
each citation.

### Health check

```bash
curl http://localhost:8000/health
# {"status": "ok", "artifacts_indexed": "247"}
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Server status + artifact count |
| `POST` | `/ingest` | Ingest GitHub PRs + Issues |
| `POST` | `/ingest/markdown` | Ingest local `.md` files |
| `POST` | `/query` | Semantic search with composite scoring |

Full OpenAPI docs at `http://localhost:8000/docs` when running.

---

## Roadmap

- **Day 3:** Contradiction detection · knowledge void detector · agent readiness score · Neo4j graph relationships · React dashboard
- **Days 4–8:** Jira + Slack connectors · multi-tenant ACL · Render + Vercel deploy
- **Days 9–12:** Agent Identity Protocol · grounded agent demo · feedback loop (agent outcomes → graph weights) · open-source launch

---

## Why this matters

The bottleneck for enterprise AI is not model capability — it is **knowledge quality**.
Agents fail not because they cannot reason, but because they reason over stale, unranked,
permission-violating information. Agentic OS is the missing infrastructure layer: a
knowledge operating system that sits between your sources and your agents.

---

*Built by [Tanay Parikh](https://github.com/Tanay126) — MS CS @ ASU · YC S2026 applicant*
