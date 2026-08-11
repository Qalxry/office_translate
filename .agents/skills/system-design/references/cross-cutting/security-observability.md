# Security, Privacy, and Observability

Use for any system exposed to users, external networks, untrusted input, sensitive data, multi-tenancy, privileged operations, regulated domains, AI tools, or production operations.

## Security Model

Define:

- Actors and trust levels.
- Assets and sensitive data.
- Entry points and untrusted inputs.
- Authentication and authorization.
- Tenant and environment boundaries.
- Privileged operations and approval gates.
- Secrets and key management.
- Audit logging and forensic needs.
- Dependency and supply-chain risk.

## Threat Modeling Prompts

- What can an unauthenticated user do?
- What can a normal authenticated user do to another user's data?
- What can an admin do, and what should require extra approval?
- Can imported, uploaded, retrieved, or third-party data become instructions or code?
- Can a callback URL, webhook, parser, file, template, query, log, or plugin become an attack path?
- What happens when config is missing or a dependency is unavailable?
- Which controls are preventive, detective, and recovery controls?

## Validation-First Security Review

For security-sensitive reviews, separate discovery from validation:

- Discovery identifies candidate attack paths, trust-boundary gaps, and abuse cases.
- Validation tries to disprove each finding with source, config, deployment, and data-flow evidence.
- Report only issues that are exploitable, decision-relevant, or explicitly accepted as defense-in-depth gaps.
- Prefer concrete traces: entry point, propagation, sink, conditions, impact, and reproduction or reasoning path.

Avoid padding reports with theoretical lows. If a concern cannot be validated, record it as an open question or hardening idea, not as a confirmed vulnerability.

## Privacy and Compliance

- Data classification, minimization, consent, retention, deletion, residency, and export.
- PII in prompts, logs, traces, analytics, backups, and vendor systems.
- Encryption in transit and at rest.
- Access review, least privilege, and break-glass process.
- Regulatory regimes such as GDPR, HIPAA, PCI, SOC 2, or local equivalents when relevant.

## Observability Architecture

Define:

- Golden signals or service-specific SLIs.
- Metrics for business and system health.
- Structured logs for state transitions and errors.
- Distributed traces across service and queue boundaries.
- Audit events for security-sensitive actions.
- Dashboards for operators.
- Alerts tied to SLOs and user impact, not noisy internals.
- Runbooks for likely incidents.

## AI/Agentic Extra Checks

- Prompt injection from retrieved content, web pages, tool output, user files, and external messages.
- Tool permission boundaries and side effects.
- Data exfiltration through model output, tool calls, logs, traces, or citations.
- Cost and rate-limit abuse.
- Human approval for writes, external communication, or destructive actions.
- Eval traces that do not leak secrets.

## Review Smells

- "Use JWT" or "use OAuth" is the entire security design.
- Authenticated means authorized.
- Tenant id is client supplied without server-side enforcement.
- Logs contain secrets, tokens, raw prompts, or personal data without policy.
- Alerting exists but no one owns response.
- No traceability for event-driven or async failures.
- AI tools can read/write broadly without least privilege.

## Expected Outputs

- Trust-boundary diagram.
- Role/permission matrix.
- Data classification and retention table.
- Security controls mapped to assets and threats.
- Observability and SLO plan.
- Incident/runbook outline.
- ADR candidates for auth strategy, tenant isolation, secrets, audit model, telemetry stack, and AI/tool policy.
