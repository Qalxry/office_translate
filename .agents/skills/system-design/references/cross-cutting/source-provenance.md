# Source Provenance

Use when recommendations depend on source freshness, vendor guidance, field practice, local inference, or low-confidence research.

## Provenance Labels

Attach a label to important recommendations:

| Label | Meaning | Use for |
| --- | --- | --- |
| `official` | Directly supported by primary vendor, standards, or project documentation. | Cloud service limits, security guidance, protocol rules, framework APIs. |
| `derived` | Reasoned from official facts plus local constraints. | Architecture trade-offs, service combinations, capacity implications. |
| `field` | Common practice or experience-backed pattern, not guaranteed by official docs. | Operational heuristics, migration tactics, team/process advice. |
| `local` | Inferred from this repository's code, docs, ADRs, or user constraints. | Existing stack decisions, naming, ownership, current architecture. |
| `uncertain` | Needs verification before commitment. | Fast-changing products, regulations, benchmarks, pricing, preview features. |

Use labels sparingly. They are for load-bearing claims, not every sentence.

## Freshness Rules

Verify current primary sources before recommending specifics for:

- Cloud services, pricing, quotas, regions, product names, SLAs, and preview/GA status.
- AI/LLM models, agent frameworks, MCP/A2A protocols, safety guidance, and eval tooling.
- Security standards, legal/regulatory requirements, compliance controls, and CVEs.
- Library/framework APIs, deprecations, runtime support windows, and deployment targets.

If current verification is unavailable, say what is assumed and mark the recommendation `uncertain`.

## Recommendation Shape

```markdown
| Recommendation | Provenance | Confidence | Verification Needed |
| --- | --- | --- | --- |
```

For mixed evidence, separate the stable principle from the current implementation detail.

Example:

- Stable principle: use workload identity over static long-lived secrets.
- Current detail: exact provider feature, CLI command, or IAM binding to verify now.

## Anti-Patterns

- Treating vendor marketing claims as independent architecture evidence.
- Hiding local inference behind confident wording.
- Citing an awesome-list as if it were a primary source.
- Using stale model, cloud, or security guidance because it sounds familiar.
- Mixing official requirements and field heuristics in one unlabeled recommendation.
