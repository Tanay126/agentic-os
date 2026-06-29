"""
VoidDetector — identifies topics the knowledge base cannot answer well.

A void is a topic queried repeatedly but with consistently low composite scores.
Knowing what we DON'T know is operationally as valuable as knowing what we do —
it tells us where to invest documentation effort.
"""

from collections import defaultdict


class VoidDetector:
    """
    Tracks query topics and their best composite scores over time.

    void_score = query_count * (1 - avg_top_score)

    A topic qualifies as a void when:
      - it has been queried MIN_QUERIES_FOR_VOID or more times, AND
      - its average top composite score is below MAX_SCORE_FOR_VOID
    """

    MIN_QUERIES_FOR_VOID = 3
    # Composite score already discounts for freshness and authority, so 0.35
    # is the right cutoff — a score below 0.35 means no meaningful documentation
    # exists for this topic in the knowledge base.
    MAX_SCORE_FOR_VOID = 0.35

    def __init__(self) -> None:
        # normalized topic → list of best composite scores, one per query
        self._scores: dict[str, list[float]] = defaultdict(list)

    def log_query(self, topic: str, top_composite_score: float) -> None:
        self._scores[topic.strip().lower()].append(top_composite_score)

    def get_voids(self, top_n: int = 10) -> list[dict]:
        """Return the top_n void topics sorted by void_score descending."""
        voids = []
        for topic, scores in self._scores.items():
            count = len(scores)
            if count < self.MIN_QUERIES_FOR_VOID:
                continue
            avg = sum(scores) / count
            if avg >= self.MAX_SCORE_FOR_VOID:
                continue
            voids.append({
                "topic": topic,
                "query_count": count,
                "avg_top_score": round(avg, 4),
                "void_score": round(count * (1 - avg), 4),
            })

        voids.sort(key=lambda v: v["void_score"], reverse=True)
        return voids[:top_n]
