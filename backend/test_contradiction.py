"""
Test: contradiction detection between two conflicting auth-token policy artifacts.

Injects an old artifact (8 months ago, "24 hours") and a new one (last week,
"4 hours"), then verifies that /query returns a contradiction_alert on the older
result and that the newer result is clean.
"""

import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Run from backend/ with the venv activated.
sys.path.insert(0, str(Path(__file__).parent))

from app.models.event import Event
from app.services.ingestion import IngestionService

TEST_DATA_DIR = "/tmp/test_contradiction_data"


def make_event(content: str, days_ago: int) -> Event:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return Event(
        source="markdown",
        event_type="markdown_doc",
        actor="test",
        timestamp_event=ts,
        artifact_id=f"test_auth_{uuid.uuid4().hex[:8]}",
        title=content[:50],
        content=content,
        allowed_groups=["engineering"],
        metadata={"authority_score": 0.85},
    )


def main() -> None:
    # Fresh isolated store so this test never touches production data
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    svc = IngestionService(data_dir=TEST_DATA_DIR)

    old_event = make_event(
        "Auth tokens expire after 24 hours. Clients must refresh before expiry "
        "to maintain a valid session. Refresh tokens are valid for 30 days.",
        days_ago=240,  # ~8 months ago
    )
    new_event = make_event(
        "Auth tokens now expire after 4 hours for security. This change takes "
        "effect immediately. Refresh tokens are valid for 30 days.",
        days_ago=7,  # last week
    )

    print("Ingesting old event (240 days ago) ...")
    svc.ingest_events([old_event])
    print("Ingesting new event (7 days ago) ...")
    svc.ingest_events([new_event])

    print("\nQuerying for 'token expiry' ...")
    results = svc.query(
        query_text="token expiry",
        user_id="test",
        groups=["engineering"],
        tenant_id="default",
        n_results=5,
    )

    print(f"\nReturned {len(results)} result(s):\n")
    flagged = 0
    for r in results:
        print(f"  artifact_id  : {r['artifact_id']}")
        print(f"  title        : {r['title'][:60]}")
        print(f"  composite    : {r['scores']['composite']}")
        print(f"  contradiction_risk : {r.get('contradiction_risk', 0.0)}")
        print(f"  contradiction_alert: {r.get('contradiction_alert')}")
        print(f"  timestamp_event    : {r['timestamp_event']}")
        print()
        if r.get("contradiction_alert"):
            flagged += 1

    assert flagged >= 1, (
        "FAIL: expected at least one result with contradiction_alert set, got 0"
    )
    print(f"PASS: {flagged} result(s) have contradiction_alert populated.")

    # Verify the older artifact is the one flagged, not the newer
    flagged_results = [r for r in results if r.get("contradiction_alert")]
    for r in flagged_results:
        ts = datetime.fromisoformat(r["timestamp_event"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - ts).days
        assert age_days > 30, (
            f"FAIL: flagged artifact is only {age_days} days old — expected the older one"
        )
        print(f"PASS: flagged artifact is {age_days} days old (correct — the older one).")

    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    print("\nAll contradiction tests passed.")


if __name__ == "__main__":
    main()
