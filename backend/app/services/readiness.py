"""
AgentReadinessScorer — estimates whether an AI agent can safely execute a workflow.

Readiness is a multiplicative composite of coverage, freshness, and contradiction
signal. A low score means the agent would operate on stale, missing, or conflicting
information — a meaningful operational risk.
"""

from typing import Any


def get_agent_readiness(workflow_name: str, ingestion_service) -> dict[str, Any]:
    """
    Query the knowledge base for workflow_name and compute a readiness score.

    readiness = doc_coverage × freshness × contradiction_free

    Recommendation thresholds:
      > 0.7   → "Safe to automate"
      0.4–0.7 → "Needs review"
      < 0.4   → "Do not automate"
    """
    # Query as an engineering-scoped agent — readiness checks what the agent
    # can access, which mirrors the permissions of the engineering group.
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

    readiness = doc_coverage * freshness * contradiction_free

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
        },
        "recommendation": recommendation,
    }
