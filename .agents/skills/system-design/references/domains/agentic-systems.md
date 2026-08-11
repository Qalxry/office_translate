# Agentic and LLM Systems

Use for LLM assistants, RAG products, tool-using agents, copilot workflows, multi-agent systems, MCP/A2A integrations, evaluation harnesses, and AI automation.

## First Questions

- What role is the AI playing: transformer, tutor, analyst, planner, tool-using agent, reviewer, or executor?
- What actions can it take, and which require approval?
- What tools, data, memory, and external systems can it access?
- What must be grounded in sources?
- What are latency, cost, safety, privacy, and reliability targets?
- How will quality regressions be detected?

## Core Architecture Components

- User/session interface.
- Orchestrator or agent loop.
- Model provider boundary.
- Tool registry and permission policy.
- Retrieval/grounding layer.
- Memory/state store.
- Evaluation and trace store.
- Human approval gates.
- Safety filters and prompt-injection defenses.
- Observability: traces, tool calls, model inputs/outputs, cost, latency, failures.

## Agent Loop Design

Define:

- Planning style: no-plan, explicit plan, hidden scratchpad, state machine, workflow graph.
- Tool contract: schemas, side effects, timeout, retry, idempotency, auth, output validation.
- Step bounds: max steps, cost ceiling, token budget, wall-clock timeout.
- Approval gates: writes, external messages, purchases, destructive ops, secrets, permissions.
- Recovery: retry, ask user, degrade, hand off, or stop.
- Auditability: who did what, with which evidence and approval.

## Multi-Agent Design

Use multiple agents only when independent perspectives or parallel context windows improve quality.

- Split by responsibility: researcher, designer, security reviewer, data reviewer, implementation planner.
- Avoid agents negotiating vague goals with each other.
- Main orchestrator owns synthesis and conflict resolution.
- Feed subagents raw constraints and artifacts, not the preferred answer.
- Persist useful outputs as design docs, ADRs, evals, or proposal entries.

## Agent Architecture Taxonomy

Choose the simplest control shape that satisfies the workflow:

| Shape | Use when | Watch for |
| --- | --- | --- |
| Single prompt/tool call | Task is bounded and reversible | Hidden state and poor auditability |
| Deterministic workflow | Steps are known and correctness matters | Too little flexibility for messy inputs |
| State machine or graph | Branching, retries, approvals, or long-running work matter | State explosion and unclear ownership |
| Planner-executor | Work needs decomposition plus tool use | Over-planning and unbounded loops |
| Multi-agent review | Independent perspectives materially improve quality | Coordination overhead and duplicate work |

For architecture design agents, a workflow/state machine is often clearer than open-ended multi-agent negotiation.

## Safety and Security

- Treat retrieved content, tool output, web pages, files, user uploads, and external messages as untrusted.
- Separate instructions from data.
- Do not let tool output grant itself authority.
- Enforce least privilege per tool and per tenant.
- Validate tool output before using it in decisions.
- Log prompt/tool traces carefully without leaking secrets or PII.
- Include prompt-injection, data exfiltration, unsafe tool use, runaway cost, and hallucinated action risks.

## Evaluation

- Task success evals for core workflows.
- Retrieval evals for RAG.
- Groundedness/faithfulness checks.
- Tool-use correctness and side-effect safety.
- Regression tests for prompts, model upgrades, routing, and memory changes.
- Human review for high-impact actions.

## Production Agent Gates

- Tool registry has schemas, permissions, side-effect classes, and timeouts.
- Each write or external side effect has an approval policy.
- Prompt/tool/model traces are retained enough for debugging without leaking secrets.
- Model/provider fallback is defined for outage, rate limit, degraded quality, and cost spikes.
- Agent outputs that affect users have evals or review samples before release.
- Memory has retention, deletion, tenant isolation, and poisoning defenses.

## Review Smells

- LLM drawn as one box with no retrieval, tools, memory, eval, or policy boundary.
- Agent can call tools indefinitely.
- No approval boundary for external side effects.
- Tool output is trusted as instruction.
- No citation or provenance for answers over private data.
- No budget for tokens, latency, rate limits, or provider outage.
- "Multi-agent" added where one workflow/state machine would be clearer.

## Expected Outputs

- Agent role matrix.
- Tool inventory and permission policy.
- Retrieval and memory design.
- Agent loop/state diagram.
- Evaluation plan.
- Safety and approval matrix.
- ADR candidates for model/provider, orchestration framework, memory store, tool policy, and MCP/A2A boundary.
