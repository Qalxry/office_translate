# Language and Runtime Selection

Programming language is an architecture decision only when it is load-bearing. Do not start with language debates; start with constraints.

Treat language as a cross-cutting decision, not a primary system taxonomy. First classify the system by workload and failure mode; then evaluate language/runtime only where it affects the architecture.

## When It Is Architecture-Level

Evaluate language/runtime explicitly when it affects:

- Concurrency model, throughput, tail latency, startup time, memory footprint, or CPU efficiency.
- Deployment target: browser, mobile, serverless, containers, embedded, edge, GPU, data notebooks, or managed platform.
- Ecosystem: web frameworks, data/AI libraries, database clients, cloud SDKs, observability, security tooling.
- Type safety and interface stability across teams or public APIs.
- Memory safety for parsers, network daemons, plugins, agents executing tools, or untrusted input.
- Team skills, hiring, existing codebase conventions, and long-term maintainability.
- Build, packaging, cross-platform delivery, or operational debugging.
- Vendor or framework lock-in.

If none apply, follow the existing stack or choose the simplest familiar runtime.

## Comparison Axes

| Axis | Questions |
| --- | --- |
| Workload fit | CPU-bound, IO-bound, realtime, batch, streaming, GPU, UI, embedded? |
| Concurrency | Event loop, threads, async/await, actors, green threads, processes? |
| Safety | Static types, memory safety, null safety, sandboxing, dependency hygiene? |
| Ecosystem | Are critical libraries mature for the domain? |
| Operations | Cold start, container size, profiling, tracing, logs, packaging, deploy target? |
| Interfaces | Does the language shape API schemas, SDKs, generated clients, ABI, or plugin model? |
| Team | Can the team maintain, debug, hire for, and review it? |
| Evolution | How painful is migration, polyglot operation, or version upgrade? |

## Common Defaults

- Existing coherent repo stack: keep it unless a constraint says otherwise.
- Web SaaS backend: TypeScript/Node, Python, Go, Java/Kotlin, C#/.NET, Ruby, or PHP can all be valid. Pick for team, ecosystem, latency, and operational fit.
- High-throughput network services: Go, Rust, Java, C++, or Erlang/Elixir often deserve consideration.
- Data/ML systems: Python is usually the orchestration default; JVM, SQL engines, Rust, Go, or C++ may own hot paths.
- Agentic/LLM products: TypeScript or Python often fit SDK velocity; isolate providers/tools behind contracts so the runtime is not the architecture.
- Mobile/desktop/embedded: platform constraints dominate.

## Domain Pressure Examples

| System pressure | Runtime implication |
| --- | --- |
| High-throughput network proxy, parser, or plugin host | Memory safety, tail latency, and concurrency may dominate. |
| Data science, RAG prototyping, ML orchestration | Python ecosystem and notebook/debug velocity may dominate. |
| Public SaaS API with a TypeScript frontend team | Type sharing, generated clients, and hiring may favor TypeScript/Node. |
| Enterprise JVM/.NET estate | Existing ops, identity, observability, and governance may dominate. |
| Serverless edge function | Startup time, package size, platform support, and provider limits may dominate. |
| Embedded, mobile, browser, GPU, or native desktop | Platform toolchain dominates the choice. |

## ADR Trigger

Create an ADR candidate when language/runtime choice:

- Sets the long-term service template.
- Changes public extension/plugin APIs.
- Requires team reskilling.
- Is chosen for non-obvious constraints such as memory safety, p99 latency, cold start, or regulated deployment.
- Deviates from the existing project stack.

## Anti-Patterns

- Choosing a language because it is fashionable.
- Using micro-benchmarks to decide an IO-bound product.
- Ignoring deployment and debugging ergonomics.
- Using polyglot services before team and operations can support them.
- Treating framework choice as reversible when it defines data model, routing, auth, or API contracts.
