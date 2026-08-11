# Cloud-Native and Platform Architecture

Use for cloud deployments, platform engineering, Kubernetes, serverless, PaaS, infrastructure as code, managed identity, observability, cost, and migration to cloud.

## First Questions

- What is being deployed: app, API, worker, data platform, agent service, internal tool, or shared platform?
- What are availability, region, data residency, identity, network, compliance, and cost constraints?
- Who operates it, and what is their skill level?
- Is the workload steady, bursty, long-running, GPU-heavy, event-driven, or latency-sensitive?
- What existing cloud, IaC, CI/CD, identity, and observability standards must be followed?

## Deployment Choices

- **PaaS/App Service/Cloud Run/Container Apps**: good default for small teams and standard apps.
- **Serverless functions**: event-driven glue, bursty workloads, scheduled jobs; watch cold start, limits, and observability.
- **Kubernetes**: many services, custom scheduling, portability, service mesh, platform teams; avoid for simple apps without ops capacity.
- **VMs**: legacy, special OS/network requirements, stateful systems, or full control.
- **Managed databases and queues**: default unless control/compliance/cost requires self-hosting.
- **GPU/AI platforms**: model size, quota, autoscaling, cost, and data boundary dominate.

## Platform Obligations

- Identity: managed identity/workload identity preferred over static secrets.
- Network: ingress, egress, private endpoints, DNS, firewall, service-to-service auth.
- IaC: Terraform, Bicep, CDK, Pulumi, or existing repo standard; avoid hand-created resources.
- Environments: dev/stage/prod parity, promotion flow, config separation.
- Deployment: blue-green, canary, rollback, migrations, feature flags.
- Observability: metrics, logs, traces, dashboards, SLO alerts.
- Reliability: zones/regions, health probes, autoscaling, backups, restore drills.
- Cost: budgets, tags, right-sizing, scale-to-zero where safe, egress awareness.

## Prepare-Validate-Deploy Gate

For high-risk cloud work, split the design and rollout into:

| Stage | Output | Must not skip |
| --- | --- | --- |
| Prepare | Architecture plan, IaC outline, identity/network model, migration impact | Current-state inventory and rollback hypothesis |
| Validate | Policy/security checks, cost/quota checks, test deployment, load or smoke tests | Evidence that the plan is deployable |
| Deploy | Change execution, monitoring, cutover, rollback readiness | Verified plan status and named operator |

Do not let the same document silently change from planned to validated. Record validation evidence separately.

## Migration Concerns

- Inventory dependencies and current-state traffic/data flows.
- Define strangler, rehost, replatform, refactor, or replace.
- Plan coexistence, data migration, sync, cutover, rollback, and decommissioning.
- Avoid "big bang" unless downtime and rollback are acceptable.

## Review Smells

- Kubernetes chosen for one service because it is "cloud-native".
- No identity story except environment secrets.
- IaC exists but production changes happen manually.
- Public endpoints for resources that should be private.
- Autoscaling target lacks load test or SLO.
- No rollback plan for schema migrations.
- No cost owner or tagging standard.
- Provider-specific services chosen without exit or lock-in rationale.

## Expected Outputs

- Deployment topology.
- Environment and IaC plan.
- Identity/network/security model.
- SLO and observability plan.
- Cost and quota assumptions.
- Migration/cutover plan when relevant.
- ADR candidates for cloud provider, runtime platform, Kubernetes/serverless/PaaS, managed service choices, and IaC tool.
