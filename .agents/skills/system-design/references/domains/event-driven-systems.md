# Event-Driven Systems

Use for queues, pub/sub, streams, webhooks, event sourcing, CQRS, sagas, async APIs, delivery gateways, and integration events.

## First Questions

- Is the message a command, event notification, durable event log entry, job, or webhook delivery?
- Who owns the event schema and compatibility?
- Is ordering required globally, per entity, per tenant, or not at all?
- Are consumers one-to-one, fan-out, replayable, or customer-owned endpoints?
- What are latency, throughput, retry, retention, and delivery guarantees?
- What happens when the consumer, provider, or broker is down?

## Pattern Selection

| Need | Prefer |
| --- | --- |
| Smooth spikes or run background work | Queue |
| Notify many subscribers | Pub/sub |
| Replay, audit, high-throughput ordered history | Stream/log |
| Cross-service state change without 2PC | Outbox plus consumer idempotency |
| Long-running business transaction | Saga with explicit compensation |
| Customer endpoints or third-party callbacks | Webhook gateway/delivery service |
| Read/write model separation under load | CQRS, only when query/write asymmetry justifies it |
| Full history as state source | Event sourcing, only when audit/replay/domain fit justifies it |

## Design Obligations

- Event envelope: id, type, version, producer, timestamp, correlation id, causation id, tenant, trace context.
- Schema lifecycle: compatible changes, deprecation, consumer testing, registry or documented contract.
- Delivery semantics: at-most-once, at-least-once, effectively-once via idempotency, or exactly-once within a bounded system.
- Ordering key and partitioning strategy.
- Retry policy: backoff, jitter, max attempts, dead-letter queue, poison message handling.
- Backpressure and rate limits.
- Replay policy and replay safety.
- Observability: lag, age, attempts, failures, DLQ count, throughput, per-consumer health.

## Webhook-Specific Concerns

- Verify source signatures before processing.
- Preserve raw request body when signature schemes require it.
- Acknowledge quickly; process asynchronously when downstream work is slow.
- Deduplicate provider event ids and your own delivery ids.
- Separate inbound provider signature verification from outbound delivery signatures.
- Provide customer-visible delivery logs, retry, and endpoint health when sending webhooks.
- Treat customer-provided callback URLs as SSRF risk.

## Webhook Gateway Shape

For customer or third-party callbacks, decide explicitly:

| Concern | Design question |
| --- | --- |
| Source authentication | How is the sender verified before parsing or processing? |
| Destination authentication | How do receivers verify deliveries from this system? |
| Routing | Is routing by provider, tenant, event type, account, or customer endpoint? |
| Delivery | What is retried, for how long, with which backoff, and where are failures visible? |
| Local development | How can developers receive real test events safely? |
| Provider checklist | Which provider-specific signature, retry, and event-id rules must be followed? |

Prefer a staged workflow for implementation: setup credentials, scaffold handler, listen/test with real events, then iterate on retries, routing, and monitoring.

## Review Smells

- "Fire and forget" with no owner for failed messages.
- Consumer performs non-idempotent writes.
- No schema versioning or compatibility rule.
- Kafka or event sourcing chosen for simple async jobs.
- Sagas described without compensating actions.
- DLQ exists but no operational owner or replay process.
- Webhook handler trusts payloads because they came through a gateway.

## Expected Outputs

- Event catalog with owner and schema version.
- Async flow or C4 Dynamic diagram.
- Retry/DLQ/replay policy.
- Idempotency strategy.
- ADR candidates for broker, event ownership, saga orchestration vs choreography, event sourcing, and webhook gateway.
