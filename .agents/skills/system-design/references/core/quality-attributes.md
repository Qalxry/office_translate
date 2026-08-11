# Quality Attributes

Architecture is mostly the design of trade-offs among quality attributes. Define the attributes that matter as scenarios, not adjectives.

## Constraint Register

Use one row per load-bearing constraint.

| Operation / Scope | Attribute | Target or Assumption | Environment | Validation |
| --- | --- | --- | --- | --- |
| checkout API | latency | p95 < 300 ms | peak traffic | load test |
| order write | durability | RPO <= 5 minutes | regional outage | backup/restore drill |

If numbers are unknown, write `baseline to measure` and explain how to measure them.

## Core Attribute Prompts

- **Reliability**: What must keep working during dependency, node, zone, region, or provider failure? What is the degradation mode?
- **Availability**: What is the uptime target? What is the downtime budget? Which operations are allowed to fail?
- **Durability**: What data loss is acceptable? What are RPO and RTO?
- **Consistency**: Which data requires strong consistency? Where is eventual consistency acceptable? What happens under partition?
- **Performance**: Which operations have p50/p95/p99, throughput, freshness, or time-to-first-token targets?
- **Scalability**: What grows: users, tenants, traffic, records, files, events, tokens, models, or integrations?
- **Security**: Where are trust boundaries, privileged operations, tenant boundaries, secrets, and externally controlled inputs?
- **Privacy**: Which data is sensitive, regulated, retained, deleted, exported, logged, or sent to a provider?
- **Observability**: What metrics, logs, traces, audits, and alerts prove the system is healthy?
- **Cost**: Which dimension drives cost: requests, storage, egress, messages, tokens, GPUs, idle capacity, or engineer time?
- **Operability**: Who deploys, rolls back, responds to incidents, rotates secrets, and performs migrations?
- **Evolvability**: Which decisions are likely to change? Where should compatibility be preserved?

## Building-Block Register

After the constraint register, use a building-block table so each heavy component earns its place.

| Layer | Choice | Needed Because | Simpler Alternative | Main Trade-off |
| --- | --- | --- | --- | --- |
| compute/runtime |  |  |  |  |
| traffic/API edge |  |  |  |  |
| storage |  |  |  |  |
| cache |  |  |  |  |
| queue/stream/eventing |  |  |  |  |
| coordination/workflow |  |  |  |  |
| search/vector/analytics |  |  |  |  |
| observability |  |  |  |  |
| deployment/IaC |  |  |  |  |

Do not force every row to have a new tool. `none yet` or `existing repo standard` is often the correct answer.

## Back-of-the-Envelope Checks

Do estimates only when they drive a decision:

- QPS: daily active users * actions per user per day / 86,400 * peak factor.
- Storage: writes per day * bytes per write * retention * replication.
- Bandwidth: QPS * payload size.
- Cache: hot data fraction * object size.
- Token cost: calls * input tokens * output tokens * price/rate limits.

## Trade-Off Points

Name the trade-off instead of hiding it:

- Cache improves latency and cost but weakens freshness.
- Async queues absorb spikes but introduce delay, retry semantics, and reordering.
- Strong consistency simplifies correctness but can hurt availability or latency.
- Microservices isolate teams and deploys but add distributed failure and operations cost.
- Serverless reduces idle ops but can add cold starts, limits, and provider lock-in.
- A statically typed runtime can improve interface safety but slow iteration for some teams.

## Readiness Gate

A design is not ready when:

- There is no measurable constraint register.
- The architecture cannot explain why each heavyweight block exists.
- Failure modes are not named.
- Observability is described only as "add monitoring".
- Security is described only as "use auth".
- Unknowns are written as facts.
