"""
AgentReadinessScorer — estimates whether an AI agent can safely execute a workflow.

Readiness is a multiplicative composite of four signals:
  1. doc_coverage    — how semantically well-matched the best doc is
  2. freshness       — average temperature of top 3 results
  3. contradiction_free — penalized if any top-3 result has known contradictions
  4. content_safety  — derived from explicit risk/safety language in the top doc

The content_safety signal is what separates this from plain RAG coverage:
a runbook that says "fully reversible, no approval required" scores high;
a policy that says "irreversible, requires HR and Legal sign-off" scores low.
"""

import re
from typing import Any


# Phrases that indicate a workflow is safe to automate (boost signal)
_SAFE_PHRASES = [
    r"safe to automate",
    r"no approval required",
    r"fully automated",
    r"fully reversible",
    r"idempotent",
    r"risk level[:\s]+(?:very\s+)?low",
    r"low risk",
    r"no human approval",
    r"reversible",
]

# Phrases that indicate unconditional high operational risk (penalty signal).
# These must be strong, absolute statements — conditional approval clauses
# (e.g. "manager approval required for >$500") are NOT high risk on their own
# because the workflow has automated paths. We only penalise when the doc
# explicitly says the process must never be automated or requires HR/Legal
# sign-off (which implies legal liability, not just business policy).
_RISK_PHRASES = [
    r"never.{0,20}automat",
    r"must never be automated",
    r"do not automate",
    r"must not be automated",
    # HR/Legal sign-off implies legal/compliance risk — unconditional block
    r"(?:hr|legal)\s+(?:sign.off|sign off|clearance)\b",
    r"legal\s+(?:approval|sign.off)",
    r"irreversible",
    r"high.{0,5}stakes?",
    r"cannot be skipped",
]


def _content_safety_multiplier(doc_text: str) -> float:
    """
    Return a multiplier (0.2–1.3) derived from explicit risk/safety language.

    Strong safe signals  → 1.2–1.3
    Neutral              → 1.0
    Moderate risk signals → 0.6–0.8
    Strong risk signals  → 0.2–0.4
    """
    text = doc_text.lower()

    safe_hits = sum(
        1 for pattern in _SAFE_PHRASES if re.search(pattern, text, re.IGNORECASE)
    )
    risk_hits = sum(
        1 for pattern in _RISK_PHRASES if re.search(pattern, text, re.IGNORECASE)
    )

    if risk_hits >= 3:
        return 0.2
    if risk_hits == 2:
        return 0.35
    if risk_hits == 1 and safe_hits == 0:
        return 0.6
    if risk_hits == 1 and safe_hits >= 1:
        # Safe signals present but one risk flag — net result: caution
        return 0.85
    if risk_hits == 0 and safe_hits >= 3:
        return 1.3
    if risk_hits == 0 and safe_hits >= 1:
        return 1.15
    return 1.0


def get_agent_readiness(workflow_name: str, ingestion_service) -> dict[str, Any]:
    """
    Query the knowledge base for workflow_name and compute a readiness score.

    readiness = doc_coverage × freshness × contradiction_free × content_safety

    Recommendation thresholds:
      > 0.7   → "Safe to automate"
      0.4–0.7 → "Needs review"
      < 0.4   → "Do not automate"
    """
    results = ingestion_service.query(
        query_text=workflow_name,
        user_id="agent",
        groups=["engineering"],
        tenant_id="default",
        n_results=5,
    )

    if not results:
        return {
            "workflow": workflow_name,
            "readiness_score": 0.0,
            "breakdown": {
                "doc_coverage": 0.0,
                "freshness": 0.0,
                "contradiction_free": 1.0,
                "content_safety": 1.0,
            },
            "recommendation": "Do not automate",
        }

    doc_coverage = results[0]["scores"]["composite"]

    top_3 = results[:3]
    freshness = sum(r["scores"]["temperature"] for r in top_3) / len(top_3)

    contradiction_free = 1.0
    for r in top_3:
        if r.get("contradiction_risk", 0.0) > 0.3:
            contradiction_free = 0.5
            break

    # Fetch full content of the top result to evaluate safety language
    top_id = results[0]["artifact_id"]
    fetched = ingestion_service.collection.get(
        ids=[top_id], include=["documents"]
    )
    top_content = fetched["documents"][0] if fetched["documents"] else ""
    content_safety = _content_safety_multiplier(top_content)

    readiness = doc_coverage * freshness * contradiction_free * content_safety
    readiness = min(1.0, readiness)  # cap at 1.0

    if readiness > 0.7:
        recommendation = "Safe to automate"
    elif readiness >= 0.4:
        recommendation = "Needs review"
    else:
        recommendation = "Do not automate"

    return {
        "workflow": workflow_name,
        "readiness_score": round(readiness, 4),
        "breakdown": {
            "doc_coverage": round(doc_coverage, 4),
            "freshness": round(freshness, 4),
            "contradiction_free": contradiction_free,
            "content_safety": round(content_safety, 4),
        },
        "recommendation": recommendation,
    }
