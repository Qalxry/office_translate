# Reference Repo Lessons

Use when improving this skill or when a system-design task benefits from patterns in the local `ref_repos/` collection. Start from `ref_repos/INDEX.md`, then open the specific `INDEX.REPO.*.md` file named here if more evidence is needed.

## Architecture Workflow Patterns

| Pattern | Borrow from | Use in this skill |
| --- | --- | --- |
| Constraint register before design | `beaver` | Require measurable constraints or explicit assumptions before choosing building blocks. |
| Building-block selection table | `beaver` | Tie compute, storage, queue, cache, API, deployment, and observability choices to constraints. |
| Gate chain | `ai-architecture-toolkit`, `azure-skills` | Add clarification, validation, and deployment gates only for costly or risky decisions. |
| Mode router | `c4-skills`, `hookdeck-agent-skills` | Keep SKILL.md as router; load only relevant domain or artifact references. |
| C4 plus ADR loop | `c4-skills` | Let major diagram changes suggest ADRs; let ADRs suggest diagram updates. |
| Smart parse plus LLM fallback | `agent-architecture-review-sample` | Parse structured architecture input deterministically; use LLM fallback for messy prose. |
| Adversarial validation | `cloudflare-security-audit-skill` | Separate design finding generation from independent verification for reviews. |
| Provenance labels | `clickhouse-agent-skills` | Mark official, derived, field, local, or uncertain recommendations. |
| Scenario evals | `beaver`, `hookdeck-agent-skills`, `decisionops-skill` | Test whether the skill changes agent behavior, not only whether it reads well. |

## Domain Lessons

| Domain | Reference repos | Lesson |
| --- | --- | --- |
| Cloud/platform | `azure-skills` | Treat cloud work as decision and gate management: prepare, validate, deploy; prefer managed identity; verify current provider docs. |
| Database/data systems | `clickhouse-agent-skills` | Start from query patterns and provenance; use condition tables instead of one-size-fits-all recommendations. |
| Webhooks/events | `hookdeck-agent-skills` | Separate inbound verification, async processing, delivery health, retries, customer-visible logs, and provider checklists. |
| Network topology | `claude-network-skills` | Validate addressing, segmentation, routing, and rollback before configuration changes. |
| Security review | `cloudflare-security-audit-skill` | Report exploitable or decision-relevant issues with traceable evidence; avoid padding theoretical lows. |
| Agentic systems | `awesome-agentic-system-design`, `beaver` | Make tools, memory, evals, safety, protocol boundaries, and cost visible instead of drawing an agent as one box. |

## What Not To Copy Blindly

- Large fixed document sets for small systems; scale artifacts to risk.
- Product-specific CLI commands or vendor service names without current verification.
- Claude-specific eval harnesses or install flags without adapting to Codex and local tooling.
- Mermaid C4 syntax assumptions without render testing in the target environment.
- Enterprise architecture frameworks such as TOGAF unless the project explicitly uses them.

## When To Expand This Library

Add a new reference only when it changes a decision, catches a recurring failure, or gives future agents a better route. Do not add a file merely because another architecture topic exists.
