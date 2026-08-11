# External References and Research Map

Use this file to decide what to verify with current primary sources. Do not treat it as a frozen standard.

## Stable Architecture References

- C4 model: system context, container, component, and code views; usually Context + Container are enough. Official source: https://c4model.com/
- arc42: lightweight software architecture documentation structure, quality requirements, risks, and decisions. Official source: https://arc42.org/
- ADR / MADR: capture why a decision was made, alternatives, status, and consequences. Official sources: https://adr.github.io/ and https://adr.github.io/madr/
- SEI ATAM: quality-attribute scenarios, sensitivity points, trade-off points.
- Google SRE: SLIs, SLOs, error budgets, toil, incident response.
- ISO/IEC/IEEE 42010: architecture descriptions, stakeholders, concerns, views, and viewpoints.

## Cloud and Platform References

Verify current official guidance before naming specific services:

- AWS Well-Architected Framework: https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
- Azure Well-Architected Framework and Azure Architecture Center: https://learn.microsoft.com/en-us/azure/well-architected/ and https://learn.microsoft.com/en-us/azure/architecture/
- Google Cloud Well-Architected Framework and Architecture Center: https://docs.cloud.google.com/architecture/framework
- CNCF cloud-native definitions and landscape when discussing Kubernetes, service mesh, and platform tooling.

## AI and Agentic Systems

Verify current official or primary sources for:

- OpenAI agent guidance: https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
- Anthropic agent guidance: https://www.anthropic.com/research/building-effective-agents
- MCP specification: https://modelcontextprotocol.io/specification/2025-06-18
- Agent2Agent / A2A: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/ and https://github.com/a2aproject/A2A
- OWASP Top 10 for LLM Applications: https://genai.owasp.org/llm-top-10/
- NIST AI RMF Generative AI Profile: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence

Treat awesome-lists and blog summaries as discovery aids, not authority. Prefer official specs, primary vendor docs, standards bodies, and original papers for load-bearing decisions.

## Recent Research Directions To Watch

Use web search before relying on memory for these areas:

- AI-assisted software architecture design and architecture decision support.
- Agentic RAG, multi-agent orchestration, agent reliability, and evaluation.
- Prompt injection and tool-use security.
- Decision intelligence and decision registers for product/architecture choices.
- Cloud cost, GPU quota, AI gateway, semantic caching, and model routing patterns.
- Agent interoperability, especially MCP and A2A, because protocol versions and security guidance are moving quickly.
- Scenario evals and agent behavior testing, because framework defaults change as model capabilities change.

## Local Reference Repos Consulted During Creation

These repos informed the skill shape. For synthesized lessons, read `reference-repo-lessons.md`; for detailed evidence, start at `../../../../ref_repos/INDEX.md` from the project root when available.

- `ref_repos/beaver`: constraint register, building blocks, AI system design, review rubric.
- `ref_repos/c4-skills`: C4 workflow, Mermaid C4 rules, ADR scribe workflow.
- `ref_repos/ai-architecture-toolkit`: target/solution/data architecture documents, glossary and ADR discipline.
- `ref_repos/decisionops-skill`: decision gate and decision register thinking.
- `ref_repos/agent-architecture-review-sample`: architecture parsing, risk detection, diagram/report pipeline.
- `ref_repos/hookdeck-agent-skills`: webhook/event gateway gotchas, delivery health, signature verification, retries.
- `ref_repos/clickhouse-agent-skills`: analytical schema/query-pattern-first design and ingestion decisions.
- `ref_repos/azure-skills`: cloud deployment, managed identity, WAF, reliability, cost, diagnostics, IaC.
- `ref_repos/cloudflare-security-audit-skill`: trust-boundary reconnaissance and validation-first security findings.
- `ref_repos/claude-network-skills`: topology, segmentation, network validation, and rollback discipline.

## Research Intake Rule

When adding a new external reference, place it in one of these buckets:

- Stable standard or architecture model.
- Current vendor/provider guidance.
- Agentic systems research or framework evidence.
- Security/safety guidance.
- Local reference repository lesson.

Do not add a link unless it changes a design decision, validates a recurring gate, or improves the router.
