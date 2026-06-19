# backend/app/services/ingestion.py
"""
IngestionService — converts Events into scored Artifacts and persists them.

Why a service layer? Because ingestion has three concerns that shouldn't
live in connectors (they don't know about storage) or API routes (they
don't know about embeddings): dedup, embedding, and scoring.
"""

import os
from datetime import datetime, timezone
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from ..models.event import Event


# Lazy-loaded so the model download doesn't block import
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


class IngestionService:
    """
    Embeds Events and upserts them into ChromaDB.

    ChromaDB collection schema:
      id       → artifact_id  (stable key; upsert handles re-ingestion)
      document → event.content (the text that was embedded)
      metadata → flat dict of scalar fields for filtering and display
    """

    COLLECTION_NAME = "artifacts"

    def __init__(self, data_dir: str = "./data"):
        os.makedirs(data_dir, exist_ok=True)
        chroma_path = os.path.join(data_dir, "chroma")
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def ingest_events(self, events: list[Event]) -> dict[str, Any]:
        """
        Dedup, embed, and upsert a batch of Events.

        Returns a stats dict: {"received", "upserted", "skipped_empty"}.
        Upsert (not insert) lets re-running the connector update stale artifacts
        rather than creating duplicates.
        """
        if not events:
            return {"received": 0, "upserted": 0, "skipped_empty": 0}

        # Deduplicate within the batch by artifact_id — keep latest timestamp.
        seen: dict[str, Event] = {}
        for event in events:
            existing = seen.get(event.artifact_id)
            if existing is None or event.timestamp_event > existing.timestamp_event:
                seen[event.artifact_id] = event

        deduped = sorted(seen.values(), key=lambda e: e.timestamp_event)

        # Drop events with no embeddable content.
        skipped = 0
        to_ingest: list[Event] = []
        for event in deduped:
            if event.content and event.content.strip():
                to_ingest.append(event)
            else:
                skipped += 1

        if not to_ingest:
            return {"received": len(events), "upserted": 0, "skipped_empty": skipped}

        model = _get_model()
        texts = [e.content for e in to_ingest]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        ids = [e.artifact_id for e in to_ingest]
        metadatas = [self._build_metadata(e) for e in to_ingest]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        return {
            "received": len(events),
            "upserted": len(to_ingest),
            "skipped_empty": skipped,
        }

    def _build_metadata(self, event: Event) -> dict[str, Any]:
        """
        Flatten an Event into the scalar dict ChromaDB stores per document.

        ChromaDB metadata values must be str, int, float, or bool — no lists
        or nested dicts. We serialize lists as comma-joined strings.
        """
        authority = event.metadata.get("authority_score", 0.5)

        return {
            "event_id": event.event_id,
            "artifact_id": event.artifact_id,
            "source": event.source,
            "event_type": event.event_type,
            "actor": event.actor or "",
            "title": event.title or "",
            "url": event.url or "",
            "authority_score": float(authority),
            "temperature": 1.0,
            "usage_count": 0,
            "contradiction_risk": 0.0,
            "sensitivity_level": event.sensitivity_level,
            "tenant_id": event.tenant_id,
            "allowed_users": ",".join(event.allowed_users),
            "allowed_groups": ",".join(event.allowed_groups),
            "timestamp_event": event.timestamp_event.isoformat(),
            "timestamp_ingested": datetime.now(timezone.utc).isoformat(),
        }

    def query(
        self,
        query_text: str,
        user_id: str,
        groups: list[str],
        tenant_id: str = "default",
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Semantic search with ACL filtering and composite scoring.

        Access is a hard gate: if the user isn't in allowed_users or
        allowed_groups, the artifact is excluded regardless of similarity.
        """
        raw = self.collection.query(
            query_texts=[query_text],
            n_results=min(n_results * 4, 50),  # over-fetch before ACL filtering
            include=["documents", "metadatas", "distances"],
        )

        results = []
        docs = raw["documents"][0]
        metas = raw["metadatas"][0]
        dists = raw["distances"][0]

        for doc, meta, dist in zip(docs, metas, dists):
            # ACL gate — binary; failure means score = 0 (excluded)
            if not self._has_access(meta, user_id, groups, tenant_id):
                continue

            similarity = max(0.0, 1.0 - dist)  # cosine distance → similarity
            authority = float(meta.get("authority_score", 0.5))
            temperature = float(meta.get("temperature", 1.0))
            usage_boost = min(1.0, 1.0 + float(meta.get("usage_count", 0)) * 0.01)
            contradiction_penalty = 1.0 - float(meta.get("contradiction_risk", 0.0))

            composite = (
                similarity * temperature * authority * usage_boost * contradiction_penalty
            )

            results.append({
                "artifact_id": meta.get("artifact_id", ""),
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "source": meta.get("source", ""),
                "event_type": meta.get("event_type", ""),
                "actor": meta.get("actor", ""),
                "content_excerpt": doc[:300],
                "scores": {
                    "composite": round(composite, 4),
                    "similarity": round(similarity, 4),
                    "authority": round(authority, 4),
                    "temperature": round(temperature, 4),
                },
                "timestamp_event": meta.get("timestamp_event", ""),
            })

            if len(results) >= n_results:
                break

        results.sort(key=lambda r: r["scores"]["composite"], reverse=True)
        return results

    def _has_access(
        self,
        meta: dict[str, Any],
        user_id: str,
        groups: list[str],
        tenant_id: str,
    ) -> bool:
        if meta.get("tenant_id", "default") != tenant_id:
            return False

        allowed_users = set(filter(None, meta.get("allowed_users", "").split(",")))
        allowed_groups = set(filter(None, meta.get("allowed_groups", "").split(",")))

        # Empty ACL lists mean "everyone in the tenant" (public within org)
        if not allowed_users and not allowed_groups:
            return True

        if user_id in allowed_users:
            return True

        return bool(allowed_groups & set(groups))
