"""
ContradictionDetector — identifies conflicting factual claims between artifacts.

Why this matters: if an old doc says "tokens expire in 24h" but a new policy
says "4h", agents retrieving the old doc will give wrong answers. We detect
this at ingest time so the stale artifact is flagged before it causes harm.
"""

import re
from datetime import datetime, timezone
from typing import Any


# Regex patterns for extractable measurable facts
_DURATION_RE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*(seconds?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\b',
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r'\bv(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)\b', re.IGNORECASE)
_THRESHOLD_RE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*(requests?|users?|retries|attempts?|connections?|threads?|workers?|replicas?|instances?|calls?)\b',
    re.IGNORECASE,
)

_UNIT_ALIASES: dict[str, str] = {
    "min": "minutes", "mins": "minutes", "minute": "minutes",
    "hr": "hours", "hrs": "hours", "hour": "hours",
    "sec": "seconds", "second": "seconds",
    "day": "days", "week": "weeks", "month": "months", "year": "years",
    "request": "requests", "user": "users", "retry": "retries",
    "attempt": "attempts", "connection": "connections", "thread": "threads",
    "worker": "workers", "replica": "replicas", "instance": "instances",
    "call": "calls",
}


def _norm(unit: str) -> str:
    return _UNIT_ALIASES.get(unit.lower(), unit.lower())


def _extract_facts(text: str) -> dict[str, set]:
    """Return {unit -> set_of_values} extracted from measurable claims in text."""
    facts: dict[str, set] = {}

    for m in _DURATION_RE.finditer(text):
        facts.setdefault(_norm(m.group(2)), set()).add(float(m.group(1)))

    for m in _VERSION_RE.finditer(text):
        facts.setdefault("version", set()).add(m.group(1))

    for m in _THRESHOLD_RE.finditer(text):
        facts.setdefault(_norm(m.group(2)), set()).add(float(m.group(1)))

    return facts


def _parse_ts(ts_str: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


class ContradictionDetector:
    """
    Detects factual contradictions between pairs of artifacts.

    Flags contradictions on measurable facts (durations, versions, numeric
    thresholds). Prose-level semantic disagreements are deferred to a future
    LLM-based detector.
    """

    def detect(self, content_a: str, content_b: str) -> bool:
        """Return True if the two texts contain contradictory measurable facts."""
        facts_a = _extract_facts(content_a)
        facts_b = _extract_facts(content_b)

        for unit, vals_a in facts_a.items():
            vals_b = facts_b.get(unit)
            if vals_b is not None and vals_a != vals_b:
                return True

        return False

    def scan_collection(self, artifact_id: str, collection) -> list[str]:
        """
        Query the top 5 most similar artifacts and flag contradictions.

        Only the OLDER artifact in a contradicting pair gets contradiction_risk=0.7.
        The newer artifact (assumed to be the source of truth) stays at 0.0.
        Returns list of artifact_ids that were flagged.
        """
        fetched = collection.get(ids=[artifact_id], include=["documents", "metadatas"])
        if not fetched["ids"]:
            return []

        content = fetched["documents"][0]
        meta = fetched["metadatas"][0]
        ts_new = _parse_ts(meta.get("timestamp_event", ""))

        similar = collection.query(
            query_texts=[content],
            n_results=6,  # over-fetch so we can skip self
            include=["documents", "metadatas", "distances"],
        )

        flagged: list[str] = []
        for s_id, s_doc, s_meta, s_dist in zip(
            similar["ids"][0],
            similar["documents"][0],
            similar["metadatas"][0],
            similar["distances"][0],
        ):
            if s_id == artifact_id:
                continue

            similarity = max(0.0, 1.0 - s_dist)
            # Only compare documents that are highly semantically similar —
            # a threshold of 0.75 ensures we're comparing same-topic docs.
            # Lower thresholds produce false positives (e.g. two docs that
            # both mention "days" for unrelated facts get flagged).
            if similarity < 0.75:
                continue

            if not self.detect(content, s_doc):
                continue

            ts_other = _parse_ts(s_meta.get("timestamp_event", ""))
            new_is_newer = (
                ts_new is not None
                and ts_other is not None
                and ts_new > ts_other
            ) or ts_other is None

            if new_is_newer:
                older_id, older_meta = s_id, dict(s_meta)
            else:
                older_id, older_meta = artifact_id, dict(meta)

            older_meta["contradiction_risk"] = 0.7
            collection.update(ids=[older_id], metadatas=[older_meta])
            flagged.append(older_id)
            print(f"[contradiction] flagged {older_id!r} (risk=0.7)")

        return flagged
