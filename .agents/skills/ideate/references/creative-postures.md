# Creative Postures

Creative posture controls how far to challenge the obvious answer. It does not determine the ideation phase and does not override explicit constraints.

Choose one posture for the current response. The user may change it at any time.

## Contents

- [Posture Summary](#posture-summary)
- [Selection Priority](#selection-priority)
- [Explicit Signals](#explicit-signals)
- [Context Signals](#context-signals)
- [Respect And Agency](#respect-and-agency)
- [Behavior By Phase](#behavior-by-phase)
- [Calibration Check](#calibration-check)

## Posture Summary

| Posture | Default intent | Relationship to the premise | Typical behavior |
|---|---|---|---|
| `faithful` | Preserve and strengthen | Treat the selected direction as fixed unless it is impossible or unsafe | Fill gaps, improve coherence, compare only consequential local alternatives |
| `exploratory` | Balance originality and feasibility | Preserve the underlying goal while allowing a stronger mechanism or framing | Show meaningful alternatives, include an opinionated bet, recommend one |
| `inventive` | Discover non-nearest possibilities | Treat the stated solution as a hypothesis while preserving hard constraints | Reframe, invert, transfer mechanisms across domains, and generate structurally different concepts |

Do not describe `faithful` as inferior or `inventive` as automatically better. The correct posture depends on the user's intent and the cost of changing the premise.

## Selection Priority

1. Use the posture explicitly requested by the user.
2. Otherwise apply durable taste preferences when they are relevant and current.
3. Otherwise infer posture from wording, idea maturity, project area, risk, and reversibility.
4. Default to `exploratory` when signals are mixed or absent.
5. Ask only when choosing differently would materially change the result and there is no defensible default.

## Explicit Signals

Map natural language rather than requiring special syntax.

Choose `faithful` for requests such as:

- keep the direction fixed
- fill in the details
- make this coherent or production-ready without redesigning it
- follow the existing pattern
- reduce risk or preserve compatibility

Choose `exploratory` for requests such as:

- think this through
- compare a few approaches
- improve the idea
- make it less generic but still practical
- recommend the best direction

Choose `inventive` for requests such as:

- surprise me
- be bold, unconventional, or highly creative
- invent something I have not already described
- challenge the premise
- stop making me do the creative work
- explore a 0-to-1 direction

The user can also say "more inventive" or "more faithful" to move one step without restarting the phase.

## Context Signals

When the user does not specify posture, adjust your default with context:

- lean more `inventive` for product core, taste-sensitive UX, new workflows, 0-to-1 tools, creative direction, and ideas that risk becoming interchangeable
- lean `exploratory` for ordinary feature shaping, product trade-offs, and reversible workflow changes
- lean more `faithful` for support infrastructure, compatibility work, migrations, security boundaries, compliance, public APIs, destructive behavior, and established user commitments

These are defaults, not vetoes. An explicit user request for invention still applies in a high-risk domain, but separate creative hypotheses from facts and surface the risk instead of silently lowering ambition.

## Respect And Agency

Apply active judgment without taking ownership away from the user:

- preserve explicit hard constraints, non-goals, and vetoes
- challenge only assumptions that appear soft or prematurely chosen
- label inferred goals and premise changes as hypotheses
- offer a premise-challenging alternative rather than silently substituting it
- state a recommendation and sacrifice instead of hiding behind neutrality
- stop advocating for a rejected direction unless new evidence materially changes the trade-off

Creative agency applies to the design space. It does not authorize invented facts, fabricated user research, ignored safety constraints, or unauthorized implementation.

## Behavior By Phase

### During Explore And Select

`faithful`:

- keep options close to the stated premise
- generate only enough alternatives to reveal a consequential choice
- prefer refinement of mechanism over wholesale reframing

`exploratory`:

- make the conventional path visible without letting it anchor the whole answer
- include at least one stronger, more opinionated mechanism
- compare real bets and recommend one

`inventive`:

- generate several structurally different concept families
- include non-nearest directions created by inversion, elimination, actor shift, or analogous transfer
- withhold premature feasibility pruning, but keep mechanisms coherent and constraints visible

### During Enrich And Shape

`faithful`:

- preserve the lock and fill missing scenarios, states, boundaries, and acceptance evidence
- surface problems without redesigning around them unless the user agrees

`exploratory`:

- preserve the lock while comparing local choices that affect the experience
- strengthen the signature move and remove generic details

`inventive`:

- make the selected direction more distinctive through interaction, sequencing, feedback, tone, or scope
- do not change the core mechanism silently; propose reopening exploration when invention requires a premise change

## Calibration Check

Before responding, check:

- Is the posture based on the user's real intent rather than the excitement of the topic?
- Did explicit user direction override contextual inference?
- Is `faithful` still offering judgment rather than acting as a transcription service?
- Is `exploratory` producing a real fork rather than one safe answer plus decoration?
- Is `inventive` changing premises or mechanisms rather than adding feature volume?
- Would moving one posture up or down better reduce the user's cognitive burden?

If calibration is weak, adjust posture before applying the phase workflow.
