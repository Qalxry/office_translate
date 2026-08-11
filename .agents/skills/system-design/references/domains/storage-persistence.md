# Storage and Persistence Architecture

Use for transactional databases, persistence models, cache layers, schema migration, backup/restore, retention, deletion, consistency, and data ownership in operational systems.

## First Questions

- What data is the source of truth, and who owns it?
- Which invariants must be transactionally protected?
- What are read/write patterns, latency, throughput, cardinality, and growth?
- Which queries must be fast now, and which can be asynchronous or analytical?
- What consistency, durability, RPO/RTO, retention, deletion, and compliance targets exist?
- What migrations, backfills, imports, exports, and rollback paths are expected?

## Store Selection

| Need | Prefer |
| --- | --- |
| Relational state, constraints, transactions, reporting joins | Relational OLTP |
| Key lookup at massive scale with simple access patterns | Key-value or wide-column store |
| Document lifecycle with flexible nested shape | Document store, only when query patterns fit |
| Shared cache, rate limiting, ephemeral coordination | Redis-like cache, not source of truth |
| Full-text search, faceting, relevance | Search index fed from source of truth |
| Time-series metrics or observability | Time-series or columnar store |
| Audit/replay/history as core domain model | Event log/event sourcing, only when domain fit is real |

Default to a relational database for core transactional state unless access patterns, scale, or platform constraints justify otherwise.

## Data Ownership

- One writer owns each table, collection, stream, or aggregate.
- Cross-service reads use APIs, read models, replicas, or events; do not share write ownership silently.
- Keep API DTOs, domain objects, persistence models, and analytics models separate when their lifecycles differ.
- Define tenant key, permission filter, and row/object-level isolation for multi-tenant data.

## Cache and Derived State

- State what the source of truth is.
- Define cache key, freshness, invalidation, TTL, stampede protection, and fallback behavior.
- Treat search indexes, read models, vector stores, and analytics marts as derived unless intentionally promoted to source of truth.
- Make rebuild/backfill/replay possible for derived stores.

## Migration and Recovery

- Schema changes need expand/contract or compatibility plan for zero-downtime services.
- Backfills need batching, observability, retry, and pause/resume.
- Backup/restore must be tested, not only configured.
- Retention and deletion must cover primary, derived, backup, log, prompt, and export copies.
- Rollback strategy must address schema, data, code, and cache/index versions.

## Review Smells

- Database chosen before access patterns and invariants are known.
- Multiple services write the same data without ownership.
- Cache is required for correctness.
- Migration plan assumes downtime but product did not accept downtime.
- No restore drill, RPO/RTO, or deletion story.
- Analytics queries run on the transactional primary without isolation.
- Vector/search index added without source offsets, permissions, rebuild, and evaluation.

## Expected Outputs

- Data ownership table.
- Query/access pattern table.
- Store and cache decision table.
- Schema migration and backfill plan.
- Backup/restore and retention plan.
- ADR candidates for database choice, data ownership, cache policy, event sourcing, and migration strategy.
