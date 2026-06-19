cat > ~/Desktop/agentic-os/CLAUDE.md << 'CLAUDEOF'
# Agentic OS — Claude Code Project Memory

## WHY
Building the "Company Brain" — a temporal knowledge graph for enterprise AI
that makes agents smarter by giving them freshness-scored, authority-weighted,
permission-aware knowledge. Target: YC S2026 application by end of June 2026.
Founder: Tanay Parikh, MS CS @ ASU, GPA 4.0, 2026.

## WHAT (Architecture)

### The core insight
Standard RAG retrieves semantically similar docs that may be months out of date.
We add three signals plain RAG lacks:
- Temperature: freshness decay over time
- Authority: merged PR=0.85 > Slack=0.40, ADR=0.95, runbook=0.90
- Permission-coherence: agents never see what their authorizing human cannot

### Tech stack
- Backend: Python 3.13, FastAPI, uvicorn
- Vector DB: ChromaDB (local persistent)
- Graph DB: Neo4j (Docker, Day 2)
- Embeddings: sentence-transformers all-MiniLM-L6-v2 (local, no API key)
- Frontend: React + Vite (Day 3)
- Deploy: Render (backend) + Vercel (frontend)

### Project location
/Users/tny/Desktop/agentic-os/

### Folder structure
backend/
  app/
    connectors/   — GitHub, Jira, Slack, Markdown connectors
    models/       — Pydantic schemas: Event, Artifact
    services/     — Ingestion, scoring, retrieval logic
    api/          — FastAPI route handlers
    main.py       — FastAPI app entry point
  data/           — ChromaDB + artifacts.json (gitignored)
  test_day1.py    — Day 1 smoke test (PASSING)
  .env            — Secrets (gitignored)

### Data flow
Sources → Event (normalized) → IngestionService →
Artifact (with scores) → ChromaDB (vectors) + Neo4j (graph) →
Retrieval (ACL filter → semantic → graph expand → rerank) →
/query API → citations + confidence scores

### Event schema (core contract)
Every source produces Events:
event_id, source, event_type, actor, timestamp_event, timestamp_ingested,
artifact_id, content, title, url, allowed_users, allowed_groups,
sensitivity_level, tenant_id, linked_artifact_ids, metadata

### Thermodynamic scoring
- temperature: T(t) = T_ambient + (T(t-1) - T_ambient) * exp(-k * delta_t)
- authority_score: ADR=0.95, runbook=0.90, merged_PR=0.85, issue=0.70, slack=0.40
- usage_count: increments on every retrieval
- contradiction_risk: 0.0-1.0, set by contradiction detector

### Retrieval formula
Score(q,i) = Access(user,i) x Sim(q,xi) x Freshness(i) x Authority(i) x Usage(i) x GraphBoost(i)
Access is a HARD binary gate — 0 means unretrievable regardless of other scores.

## HOW (Commands)

### Activate Python environment (always do this first)
cd /Users/tny/Desktop/agentic-os/backend
source venv/bin/activate

### Run the backend API
uvicorn app.main:app --reload --port 8000

### Run Day 1 test
python test_day1.py

### Install new packages
pip install <package> && pip freeze > requirements.txt

### Environment variables needed in backend/.env
GITHUB_TOKEN=ghp_...
ANTHROPIC_API_KEY=sk-ant-...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=agentikos

## Build progress

### DONE (Day 1)
- [x] Project structure
- [x] Python 3.13 venv + all dependencies installed
- [x] Event + Artifact Pydantic models (models/event.py)
- [x] GitHub connector — PRs + Issues to Events (connectors/github.py)
- [x] IngestionService — dedup, sort by event time, embed, store (services/ingestion.py)
- [x] ChromaDB integration — persistent local vector store
- [x] test_day1.py — PASSING on fastapi/fastapi public repo
- [x] .gitignore created
- [x] CLAUDE.md created

### TODO (Day 2 — current priority)
- [ ] FastAPI main.py — wire up the app with lifespan, CORS, routers
- [ ] GET /health endpoint
- [ ] POST /ingest endpoint — trigger GitHub ingestion via API
- [ ] POST /query endpoint — composite scoring retrieval with citations
- [ ] Freshness decay service — background task, runs every hour
- [ ] Authority scoring — by source type at retrieval time
- [ ] Markdown connector — ingest local .md files
- [ ] requirements.txt — freeze current dependencies
- [ ] Git init + first commit

### TODO (Day 3)
- [ ] Contradiction detection
- [ ] Knowledge void detector  
- [ ] Agent readiness scoring
- [ ] React dashboard (Vite)
- [ ] Neo4j Docker setup + graph relationships

### TODO (Days 9-12)
- [ ] Agent Identity Protocol (AIP)
- [ ] Grounded agent demo
- [ ] Feedback loop — agent outcomes feed back into graph
- [ ] Open source GitHub launch + HN post

## Key decisions
1. ChromaDB first — no Docker needed for Day 1, migrate to pgvector at scale
2. JSON artifact store Day 1 — PostgreSQL Day 2+
3. sentence-transformers locally — no API key, works offline, fast on M1
4. Public GitHub repo as demo data — no token needed
5. Authority scores set at connector level — source knows its own trust level
6. Sort by timestamp_event not timestamp_ingested — correct causal ordering

## Coding conventions
- Every file has a docstring explaining what it does and WHY
- Pydantic models for all data — no raw dicts between layers
- Comments explain WHY not WHAT
- No hardcoded secrets — always os.getenv()
- After any schema change: check all consumers
- After new install: pip freeze > requirements.txt
- Before committing: run test_day1.py
CLAUDEOF