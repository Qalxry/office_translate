# System Design Reference Router

Load this file first, then load only the references that match the user's system. Prefer one primary domain, one cross-cutting concern, and the smallest core artifact set that can answer the request.

## Knowledge Layers

| Layer | Purpose |
| --- | --- |
| `core/` | Reusable architecture mechanics: quality attributes, artifacts, decisions, and late-stage review. Load by trigger. |
| `domains/` | System-type guidance: web services, storage, event-driven systems, data/AI, agentic systems, cloud platforms, enterprise integration, networks, and client/edge systems. |
| `cross-cutting/` | Concerns that can apply to any domain: runtime choice, security/observability, validation gates, and provenance. |
| `research/` | External standards, current-source research map, and lessons from local reference repositories. |

## Core References

| Reference | Load when |
| --- | --- |
| `core/architecture-artifacts.md` | Writing persistent design docs, C4 views, implementation handoff, or diagram guidance. |
| `core/quality-attributes.md` | Any non-trivial production architecture or architecture review. |
| `core/decision-records.md` | ADRs, decision registers, architecture governance, or hard-to-reverse choices. |
| `core/review-checklist.md` | Late-stage review or finalization of any design. |

## Domain References

| System type | Primary reference | Adjacent references |
| --- | --- | --- |
| Web app, SaaS backend, CRUD API, BFF, public API | `domains/web-services.md` | `cross-cutting/security-observability.md`, `cross-cutting/language-runtime-selection.md` |
| Transactional storage, database choice, cache, schema migration, persistence, backup/restore | `domains/storage-persistence.md` | `domains/web-services.md`, `domains/data-ai-systems.md`, `cross-cutting/security-observability.md` |
| Microservices, queues, webhooks, pub/sub, streams, sagas | `domains/event-driven-systems.md` | `domains/web-services.md`, `cross-cutting/security-observability.md` |
| Data platform, analytics, warehouse, streaming analytics, ML/RAG data layer | `domains/data-ai-systems.md` | `domains/event-driven-systems.md`, `domains/agentic-systems.md` |
| LLM assistant, RAG product, tool-using agent, multi-agent workflow | `domains/agentic-systems.md` | `domains/data-ai-systems.md`, `cross-cutting/security-observability.md` |
| Cloud deployment, platform engineering, Kubernetes, serverless, enterprise infra | `domains/cloud-native-platforms.md` | `cross-cutting/security-observability.md`, `cross-cutting/language-runtime-selection.md` |
| Enterprise app integration, vendor systems, ERP/CRM, cross-domain capability design | `domains/enterprise-integration.md` | `domains/event-driven-systems.md`, `domains/data-ai-systems.md` |
| Network/service topology, routing, segmentation, gateway, DNS, VPN, edge network | `domains/network-systems.md` | `cross-cutting/security-observability.md`, `domains/cloud-native-platforms.md` |
| Client app, mobile, desktop, browser app, offline sync, edge UI/runtime | `domains/client-edge-systems.md` | `domains/web-services.md`, `domains/storage-persistence.md`, `cross-cutting/security-observability.md` |
| Security-sensitive, regulated, multi-tenant, externally exposed, high-availability overlay | `cross-cutting/security-observability.md` | selected primary domain reference, `core/quality-attributes.md` |

## Cross-Cutting References

| Reference | Load when |
| --- | --- |
| `cross-cutting/language-runtime-selection.md` | Language, runtime, framework, deployment target, or team skill could shape the architecture. |
| `cross-cutting/security-observability.md` | External exposure, sensitive data, multi-tenancy, privileged operations, AI tools, or production operation. |
| `cross-cutting/evaluation-and-gates.md` | The design needs readiness gates, scenario evals, approval points, evidence, or production validation. |
| `cross-cutting/source-provenance.md` | Recommendations need source confidence labels, current-source verification, or explicit uncertainty. |

## Research References

| Reference | Load when |
| --- | --- |
| `research/external-references.md` | The task needs current architecture standards, cloud guidance, AI safety/security, or source links. |
| `research/reference-repo-lessons.md` | You are improving this skill or need patterns from indexed local reference repositories. |

## Selection Heuristic

1. Ask "what must be true for this system to be correct under stress?"
2. Pick the reference whose failure modes dominate the answer.
3. Add one adjacent reference only if another domain owns a load-bearing risk.
4. Use `cross-cutting/language-runtime-selection.md` when the runtime could become an ADR.
5. Use `core/decision-records.md` when the answer would otherwise bury rationale in prose.

Examples:

- A payment webhook receiver: `domains/event-driven-systems.md`, `cross-cutting/security-observability.md`.
- A multi-tenant SaaS API: `domains/web-services.md`, `cross-cutting/security-observability.md`.
- A ClickHouse observability platform: `domains/data-ai-systems.md`, `domains/cloud-native-platforms.md`.
- A RAG support assistant: `domains/agentic-systems.md`, `domains/data-ai-systems.md`, `cross-cutting/security-observability.md`.
- An AKS migration: `domains/cloud-native-platforms.md`, `core/quality-attributes.md`.
- A mobile offline-first field app: `domains/client-edge-systems.md`, `domains/storage-persistence.md`, `cross-cutting/security-observability.md`.

For any non-trivial production system, also load `core/quality-attributes.md` even when it is not listed in the example.
