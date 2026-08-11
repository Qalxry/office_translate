# Web Services and SaaS Backends

Use for web apps, REST/GraphQL APIs, BFFs, SaaS products, admin tools, and customer-facing services.

## First Questions

- What are the primary workflows and critical request paths?
- Which users, tenants, roles, and external systems exist?
- What data does the service own? What data is referenced from elsewhere?
- Which operations require strong consistency?
- What are p95 latency, throughput, availability, and compliance expectations?
- Is this public API, internal API, browser BFF, mobile backend, or integration endpoint?

## Architecture Choices

- **Modular monolith first**: prefer when one team owns the product, deployment coupling is acceptable, and domain boundaries are still learning.
- **Microservices**: choose when independent ownership, scaling, deployment, fault isolation, or regulatory boundaries justify distributed complexity.
- **BFF**: use when client-specific orchestration or auth/session handling would pollute domain services.
- **API gateway**: use for cross-cutting edge concerns: routing, auth, rate limits, TLS, request shaping, and observability.
- **REST**: default for resource APIs and broad compatibility.
- **GraphQL**: use for client-shaped aggregation across many sources, with explicit complexity, auth, caching, and schema governance.
- **gRPC**: use for typed internal service-to-service APIs or low-latency streaming.

## Service Boundary Gate

Before splitting services, answer:

| Question | If unclear |
| --- | --- |
| Who owns each service and its on-call? | Stay modular inside one deployable unit. |
| Which data does each service own exclusively? | Do not split the database writes. |
| Which failure should be isolated? | A module boundary may be enough. |
| Which scale dimension differs materially? | Measure before distributing. |
| Which API/event contract will remain compatible? | Do not create a public boundary yet. |

Distributed boundaries are expensive. Use them when ownership, scaling, reliability, security, or compliance constraints pay for the cost.

## Data and State

- Define source of truth per domain object.
- Separate input DTOs, domain model, persistence model, and API response model when their lifecycles differ.
- Use relational storage for transactional relational state unless access patterns demand otherwise.
- Add cache only with a freshness/invalidation story.
- Use outbox/idempotency for writes that trigger external effects.
- Never let multiple services write the same database tables without an ownership rule.

## Public API Contract Checklist

- Versioning and compatibility policy.
- Auth, scopes, tenant isolation, and rate limits.
- Idempotency for retryable writes.
- Pagination, filtering, sorting, and consistency expectations.
- Error shape, correlation id, and support/debug path.
- Deprecation, migration, and client SDK strategy when relevant.

## Security and Tenancy

- Define authN, authZ, identity propagation, session/token lifecycle, tenant isolation, admin boundaries, and audit logging.
- Validate external input at boundaries; treat third-party API responses as untrusted.
- Apply rate limiting and abuse controls at public edges.
- Avoid leaking internal identifiers, stack traces, permission details, and sensitive data in logs.

## Review Smells

- "Service" names are technical roles only: `UserService`, `DataService`, `Manager`.
- No tenant boundary or role matrix in a multi-tenant product.
- API behavior depends on undocumented ordering, timing, or error text.
- Background jobs mutate state without the same authorization or validation model.
- Retryable writes lack idempotency.
- Public API changes are not versioned, additive, or migration-safe.
- Observability cannot answer "which tenant/user/request failed and why?"

## Expected Outputs

- Context and Container diagram.
- API surface summary with auth, errors, pagination, idempotency, and rate limits.
- Data ownership table.
- Critical request path sequence.
- ADR candidates for service split, database choice, public API style, auth strategy, and tenant isolation.
