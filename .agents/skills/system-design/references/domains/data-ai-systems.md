# Data, Analytics, and AI Data Systems

Use for data platforms, analytics, warehouses, lakehouses, streaming analytics, operational analytics, ML pipelines, RAG data layers, and high-volume telemetry/search systems.

## First Questions

- What decisions or product behavior depend on the data?
- What are sources, owners, freshness needs, retention, privacy classification, and consumers?
- Is the workload transactional, analytical, search, vector retrieval, time-series, graph, stream processing, or batch?
- What are query patterns before choosing storage layout?
- What data quality, lineage, governance, and audit requirements exist?
- What scale drives design: ingest rate, query concurrency, history, cardinality, or model/token cost?

## Storage and Processing Choices

- **Relational OLTP**: transactional state and invariants.
- **Columnar warehouse/OLAP**: large scans, aggregations, observability, analytics.
- **Search index**: text relevance, filtering, logs, faceting.
- **Time-series store**: metrics and retention by time.
- **Object storage/lake**: cheap durable raw and curated data.
- **Stream processor**: low-latency transformations and windows.
- **Vector index**: semantic retrieval for RAG, tied to embedding model and chunking.
- **Graph**: relationship-heavy traversals.

## Data Architecture Obligations

- Define canonical data objects and source of truth.
- Document query patterns before physical schema, partitioning, clustering, or sort keys.
- Separate raw, cleaned, curated, serving, and feature/index layers when useful.
- Define retention, deletion, backfill, replay, and reprocessing.
- Track lineage from source to derived artifact.
- Define data quality checks and ownership.
- For analytical systems, protect against unbounded queries with limits, budgets, profiles, and explain plans.

## Query-Pattern-First Design

Before choosing a data store or physical layout, write the top query patterns:

| Pattern | Freshness | Filter / Join / Group Keys | Cardinality | SLA | Owner |
| --- | --- | --- | --- | --- | --- |

Then map each storage decision to a pattern. For database and analytics recommendations, prefer condition tables over one-size-fits-all advice:

| Condition | Recommended Path | Provenance | Trade-off |
| --- | --- | --- | --- |

Use `official`, `derived`, `field`, `local`, or `uncertain` provenance labels from `../cross-cutting/source-provenance.md` when the recommendation depends on vendor-specific rules or field practice.

## Safe Data-Agent Workflow

For agents querying databases or analytics systems:

1. Connect with least privilege.
2. Discover schema, ownership, keys, partitions, indexes, sample rows, and explain plans.
3. Plan bounded queries with filters and limits.
4. Execute with timeout, row limits, and cost guardrails.
5. Recover by narrowing scope, not by blindly retrying larger queries.

## AI/RAG-Specific Data Layer

- Chunking: boundaries, overlap, metadata, source offsets, tenant, permissions.
- Embedding model: version, dimensionality, re-index strategy.
- Retrieval: vector, keyword, hybrid, filters, reranking, top-k, context packing.
- Grounding: citations and deep links to source content.
- Context budget: system prompt, history, retrieved content, tool output, completion.
- Evaluation: retrieval recall/precision, faithfulness, regression set.

## Review Smells

- Storage chosen before access patterns are known.
- Physical schema cannot answer the top queries efficiently.
- Analytics and operational writes fight in the same store without isolation.
- No retention or deletion plan for regulated data.
- Vector DB added without chunking, metadata, permissions, or eval story.
- "The model reads the database" replaces retrieval design.
- Backfills and reprocessing are not addressed.

## Expected Outputs

- Source/consumer/data-object map.
- Storage and processing topology.
- Data flow with freshness and ownership.
- Query pattern table.
- Governance and retention plan.
- For RAG: retrieval architecture and eval plan.
- ADR candidates for warehouse/store, partitioning/sort key, streaming vs batch, vector strategy, and model/provider boundary.
