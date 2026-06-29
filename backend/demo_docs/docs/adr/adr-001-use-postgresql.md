# ADR-001: Use PostgreSQL as Primary Database

**Status:** Accepted  
**Date:** 2025-09-12  
**Deciders:** Tanay Parikh (CTO), Backend Engineering team  
**Supersedes:** None  
**Superseded by:** None

---

## Context

We need a primary relational database for the Agentic OS backend. At the 
time of this decision (September 2025), we are processing approximately 
50,000 ingestion events per day across 12 tenant accounts, with projections 
to reach 2 million events per day within 18 months.

We evaluated three options:

| Option | Pros | Cons |
|--------|------|------|
| PostgreSQL | Battle-tested, pgvector extension, excellent JSON support, strong ACID guarantees | Vertical scaling limits at extreme throughput |
| MySQL | Familiarity, wide hosting support | Weaker JSON support, no native vector extension |
| CockroachDB | Horizontal scaling, distributed | Operational complexity, cost, incomplete PostgreSQL compatibility |

Key requirements:
- Must support vector similarity search (for the embedding retrieval layer)
- Must support JSONB for flexible metadata storage
- Must have mature managed hosting options (AWS RDS, Supabase, Neon)
- Must support row-level security for multi-tenant ACL enforcement
- Team must have strong operational familiarity

---

## Decision

**We will use PostgreSQL 16 as the primary database.**

Specifically:
- pgvector extension for embedding storage and similarity search (replacing 
  ChromaDB in production at >1M artifacts)
- JSONB columns for artifact metadata (avoids schema migrations for new 
  source connectors)
- Row-level security policies for tenant isolation
- Managed on AWS RDS (Multi-AZ) for production; Neon for development and staging

---

## Consequences

### Positive

- Single database for both relational data and vector search eliminates 
  the ChromaDB–PostgreSQL synchronization problem we hit during the Day 1 
  prototype
- pgvector's HNSW index matches ChromaDB's performance at our projected 
  scale (tested up to 10M vectors, < 50ms p99 latency)
- Row-level security provides tenant isolation at the database layer — 
  ACL enforcement cannot be bypassed by application bugs
- The team has 8+ years of collective PostgreSQL experience

### Negative / risks

- At >100M vectors, pgvector HNSW memory requirements become significant 
  (~100 bytes per vector × 1536 dimensions = 150GB at 100M rows). We will 
  need to partition the embeddings table or migrate to a dedicated vector DB 
  at that scale. Revisit this decision when we cross 50M artifacts.
- PostgreSQL does not natively support time-series workloads at high 
  ingest rates. If ingest throughput exceeds 50k events/second, add 
  TimescaleDB extension or route high-frequency events to a separate 
  append-only store.

### Migration path

Current ChromaDB store will be migrated to PostgreSQL + pgvector when:
1. We have >100k artifacts in a single tenant, OR
2. We begin multi-tenant production onboarding (whichever comes first)

Migration script will be added to `backend/migrations/` at that time.

---

## Revisit criteria

Re-evaluate this decision if:
- A single tenant exceeds 100M artifacts (vector memory constraint)
- Monthly RDS cost exceeds $5k (evaluate Neon or self-managed alternatives)
- A requirement for geo-distributed writes emerges (revisit CockroachDB)
