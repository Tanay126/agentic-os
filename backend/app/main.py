# backend/app/main.py
"""
FastAPI application entry point.

The lifespan context manager ensures ChromaDB and the embedding model are
initialized once at startup rather than per-request — the model load takes
~2 seconds and the persistent client needs a stable handle across requests.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .connectors.github import GitHubConnector
from .connectors.markdown import MarkdownConnector
from .services.ingestion import IngestionService
from .services.voids import VoidDetector
from .services.readiness import get_agent_readiness

load_dotenv()

# Shared service instances — initialized once during lifespan.
_ingestion: IngestionService | None = None
_void_detector: VoidDetector | None = None

DECAY_INTERVAL_SECONDS = int(os.getenv("DECAY_INTERVAL_SECONDS", "60"))


async def _decay_loop() -> None:
    """Run freshness decay on a fixed interval for the lifetime of the process."""
    while True:
        await asyncio.sleep(DECAY_INTERVAL_SECONDS)
        if _ingestion is not None:
            stats = _ingestion.run_decay_cycle()
            if stats["updated"]:
                print(f"[decay] cycle done — {stats}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ingestion, _void_detector
    data_dir = os.getenv("DATA_DIR", "./data")
    _ingestion = IngestionService(data_dir=data_dir)
    _void_detector = VoidDetector()
    print(f"[startup] ChromaDB ready at {data_dir}/chroma")

    # Auto-ingest demo docs on cold start so the Render deployment is
    # immediately queryable without a manual /ingest call.
    demo_docs_dir = os.getenv("DEMO_DOCS_DIR", "./demo_docs")
    if _ingestion.collection.count() == 0 and os.path.isdir(demo_docs_dir):
        print(f"[startup] Empty collection — ingesting demo docs from {demo_docs_dir}")
        connector = MarkdownConnector(allowed_groups=["engineering"])
        try:
            events = connector.get_events(demo_docs_dir)
            stats = _ingestion.ingest_events(events)
            print(f"[startup] Demo docs ingested: {stats}")
        except Exception as exc:
            print(f"[startup] Demo ingest failed (non-fatal): {exc}")

    task = asyncio.create_task(_decay_loop())
    yield
    task.cancel()
    print("[shutdown] Closing down")


app = FastAPI(
    title="Agentic OS — Company Brain API",
    description="Freshness-scored, authority-weighted, permission-aware knowledge retrieval.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to Vercel domain before production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    owner: str
    repo: str
    limit: int = 50


class MarkdownIngestRequest(BaseModel):
    directory_path: str


class IngestResponse(BaseModel):
    stats: dict[str, Any]
    message: str


class QueryRequest(BaseModel):
    query: str
    user_id: str = "anonymous"
    groups: list[str] = []
    tenant_id: str = "default"
    n_results: int = 5


class QueryResponse(BaseModel):
    query: str
    results: list[dict[str, Any]]
    count: int


class ReadinessRequest(BaseModel):
    workflow: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    collection_count = _ingestion.collection.count() if _ingestion else -1
    return {
        "status": "ok",
        "artifacts_indexed": str(collection_count),
    }


@app.get("/stats")
def stats() -> dict[str, Any]:
    """Return artifact count and temperature distribution for the dashboard."""
    if _ingestion is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    all_items = _ingestion.collection.get(include=["metadatas"])
    metas = all_items["metadatas"] or []

    hot = sum(1 for m in metas if float(m.get("temperature", 1.0)) > 0.8)
    warm = sum(1 for m in metas if 0.5 < float(m.get("temperature", 1.0)) <= 0.8)
    cold = sum(1 for m in metas if float(m.get("temperature", 1.0)) <= 0.5)

    return {
        "total_artifacts": len(metas),
        "temperature_buckets": {
            "hot": hot,    # > 0.8
            "warm": warm,  # 0.5 – 0.8
            "cold": cold,  # ≤ 0.5
        },
    }


@app.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    if _ingestion is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    token = os.getenv("GITHUB_TOKEN", "")
    connector = GitHubConnector(token=token, owner=req.owner, repo=req.repo)

    events = connector.get_pull_requests(limit=req.limit)
    events += connector.get_issues(limit=req.limit)

    stats_result = _ingestion.ingest_events(events)
    return IngestResponse(
        stats=stats_result,
        message=f"Ingested from {req.owner}/{req.repo}",
    )


@app.post("/ingest/markdown", response_model=IngestResponse)
def ingest_markdown(req: MarkdownIngestRequest) -> IngestResponse:
    if _ingestion is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    connector = MarkdownConnector()
    try:
        events = connector.get_events(req.directory_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    stats_result = _ingestion.ingest_events(events)
    return IngestResponse(
        stats=stats_result,
        message=f"Ingested markdown from {req.directory_path}",
    )


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    if _ingestion is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    results = _ingestion.query(
        query_text=req.query,
        user_id=req.user_id,
        groups=req.groups,
        tenant_id=req.tenant_id,
        n_results=req.n_results,
    )

    if _void_detector is not None:
        top_score = results[0]["scores"]["composite"] if results else 0.0
        _void_detector.log_query(req.query, top_score)

    return QueryResponse(query=req.query, results=results, count=len(results))


@app.get("/voids")
def voids() -> dict[str, Any]:
    """Return the top 10 knowledge void topics sorted by void_score."""
    if _void_detector is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return {"voids": _void_detector.get_voids(top_n=10)}


@app.post("/readiness")
def readiness(req: ReadinessRequest) -> dict[str, Any]:
    """Compute agent readiness score for executing a workflow."""
    if _ingestion is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return get_agent_readiness(req.workflow, _ingestion)
