# backend/app/services/ingestion.py
"""
IngestionService — converts Events into scored Artifacts and persists them.

Why a service layer? Because ingestion has three concerns that shouldn't
live in connectors (they don't know about storage) or API routes (they
don't know about embeddings): dedup, embedding, and scoring.
"""

import math
import os
from datetime import datetime, timezone
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from ..models.event import Event
from .contradiction import ContradictionDetector


# Shared ONNX-based embedding function — no PyTorch required, ~300MB RAM.
# DefaultEmbeddingFunction wraps all-MiniLM-L6-v2 via onnxruntime.
_embed: DefaultEmbeddingFunction | None = None


def _get_embed() -> DefaultEmbeddingFunction:
    global _embed
    if _embed is None:
        _embed = DefaultEmbeddingFunction()
    return _embed


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
        self._contradiction_detector = ContradictionDetector()

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

        embed = _get_embed()
        texts = [e.content for e in to_ingest]
        embeddings = embed(texts)

        ids = [e.artifact_id for e in to_ingest]
        metadatas = [self._build_metadata(e) for e in to_ingest]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        for artifact_id in ids:
            self._contradiction_detector.scan_collection(artifact_id, self.collection)

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

            freshness_warning = self._freshness_warning(meta)

            contradiction_risk = float(meta.get("contradiction_risk", 0.0))
            contradiction_alert = (
                "This result conflicts with a newer source and may be outdated."
                if contradiction_risk >= 0.5
                else None
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
                "contradiction_risk": round(contradiction_risk, 4),
                "timestamp_event": meta.get("timestamp_event", ""),
                "freshness_warning": freshness_warning,
                "contradiction_alert": contradiction_alert,
            })

            if len(results) >= n_results:
                break

        results.sort(key=lambda r: r["scores"]["composite"], reverse=True)
        return results

    def run_decay_cycle(self) -> dict[str, Any]:
        """
        Apply thermodynamic temperature decay to every artifact in the collection.

        Formula (from CLAUDE.md):
            T(t) = T_ambient + (T(t-1) - T_ambient) * exp(-k * delta_t)

        delta_t is in days since the artifact was last ingested.
        Only artifacts whose temperature shifts by more than 0.01 are logged
        so noise-free cycles stay silent.
        """
        T_AMBIENT = 0.10
        DECAY_K = 0.01  # per day; at k=0.01 half-life ≈ 69 days

        all_items = self.collection.get(include=["metadatas"])
        ids = all_items["ids"]
        metas = all_items["metadatas"]

        if not ids:
            return {"checked": 0, "updated": 0}

        now = datetime.now(timezone.utc)
        updated_ids: list[str] = []
        updated_metas: list[dict[str, Any]] = []
        logged = 0

        for artifact_id, meta in zip(ids, metas):
            t_prev = float(meta.get("temperature", 1.0))

            ingested_str = meta.get("timestamp_ingested", "")
            if not ingested_str:
                continue
            try:
                ingested = datetime.fromisoformat(ingested_str)
            except ValueError:
                continue

            if ingested.tzinfo is None:
                ingested = ingested.replace(tzinfo=timezone.utc)

            delta_days = (now - ingested).total_seconds() / 86400.0
            t_new = T_AMBIENT + (t_prev - T_AMBIENT) * math.exp(-DECAY_K * delta_days)
            t_new = max(T_AMBIENT, min(1.0, t_new))

            if abs(t_new - t_prev) < 0.001:
                continue

            new_meta = dict(meta)
            new_meta["temperature"] = t_new
            updated_ids.append(artifact_id)
            updated_metas.append(new_meta)

            if abs(t_new - t_prev) > 0.01:
                title = meta.get("title", artifact_id)[:50]
                print(
                    f"[decay] {title!r}  "
                    f"{t_prev:.4f} → {t_new:.4f}  "
                    f"(age {delta_days:.1f}d)"
                )
                logged += 1

        if updated_ids:
            self.collection.update(ids=updated_ids, metadatas=updated_metas)

        return {"checked": len(ids), "updated": len(updated_ids), "logged": logged}

    def _freshness_warning(self, meta: dict[str, Any]) -> str | None:
        """
        Return a human-readable warning when temperature < 0.5.

        We compute age from timestamp_event (when the fact was true in the
        source system) rather than timestamp_ingested so the warning reflects
        the actual knowledge age, not when we pulled it.
        """
        temperature = float(meta.get("temperature", 1.0))
        if temperature >= 0.5:
            return None

        ts_str = meta.get("timestamp_event", "")
        if not ts_str:
            return "This result may be stale"

        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            return "This result may be stale"

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        age_days = (datetime.now(timezone.utc) - ts).days
        if age_days < 1:
            return None  # sub-day articles can't be stale enough to warn
        if age_days == 1:
            return "This result is 1 day old"
        if age_days < 30:
            return f"This result is {age_days} days old"
        months = age_days // 30
        unit = "month" if months == 1 else "months"
        return f"This result is {months} {unit} old"

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
