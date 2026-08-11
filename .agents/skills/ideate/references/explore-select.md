# Explore And Select

Use this flow when the direction is not yet selected or the user explicitly wants alternative concepts. The job is to create useful distance between options, recommend a direction, and reach a `Direction Lock` without prematurely enriching every candidate.

## Contents

- [Outcome](#outcome)
- [Workflow](#workflow)
- [Creativity Failure Check](#creativity-failure-check)
- [Anti-Patterns](#anti-patterns)

## Outcome

Finish with one of these outcomes:

- the user selects a direction
- the user deliberately combines parts of multiple directions
- the user delegates the decision and you select a direction
- one unresolved trade-off requires a focused user choice
- the user asks for another exploration pass with a different creative posture

Do not produce a detailed product brief or implementation plan before selection.

## Workflow

### 1. Infer The Latent Brief

State your current read in three to five lines:

- desired outcome
- likely user or operator
- current workaround or status quo
- success signal
- biggest assumption

Do not merely paraphrase the requested artifact. Separate what the user said they want from the job they may be trying to accomplish, and label the latter as a hypothesis.

### 2. Choose A Creative Posture

Apply the posture selected from `creative-postures.md`. Let it control distance from the stated premise, number of directions, and how aggressively to challenge conventions.

The posture changes the breadth of exploration, not the user's hard constraints.

### 3. Generate Concept Families

Generate only as many directions as create meaningful choice:

- `faithful`: usually two or three close but genuinely different directions
- `exploratory`: usually three or four directions spanning conventional and opinionated bets
- `inventive`: usually four or five structurally different directions, including non-nearest alternatives

For each direction, include only enough to compare it:

- **Thesis**: the core belief or promise
- **Mechanism**: what actually produces the outcome
- **30-second scene**: actor, trigger, action, response, proof
- **Signature move**: the memorable design decision
- **Bet and sacrifice**: what must be true and what this direction gives up
- **Refusal**: what this direction deliberately refuses to become

Do not use fixed labels such as Baseline, Sharp, or Strange unless they genuinely clarify this specific design space.

### 4. Force Structural Difference

Treat directions as duplicates when they retain the same actor, trigger, workflow, feedback loop, and value mechanism while changing only UI, technology, feature count, or naming.

If the options are duplicates, regenerate them using one or more of these moves:

- **First principles**: remove the expected artifact and solve the job directly
- **Inversion**: reverse who acts, when work happens, or what the system optimizes
- **Analogous transfer**: borrow a mechanism from another domain, not its surface styling
- **Elimination**: remove a screen, setting, step, dependency, or persistent object
- **Scale shift**: make the concept radically smaller, more ambient, more episodic, or more opinionated
- **Actor shift**: change the primary operator, beneficiary, or source of initiative

For an `inventive` posture, include at least one coherent direction that changes the premise rather than extending the obvious solution.

### 5. Recommend, Do Not Hide

Recommend one direction unless the user explicitly asks for an unranked landscape.

State:

- why it best serves the underlying outcome
- the main design bet
- the main sacrifice
- what evidence would change your recommendation

Do not choose the safest option merely because it is easiest to justify. Do not choose the strangest option merely to appear creative.

### 6. Reach The Direction Lock

If the user has already delegated selection, select the recommended direction and emit the `Direction Lock` defined in `SKILL.md`.

If the user has not selected or delegated, ask one focused choice with your recommendation first. Useful choices include:

1. accept the recommendation
2. combine two named directions
3. push the space more inventive
4. preserve more of the original premise

Do not infer acceptance from silence.

Read `enrich-shape.md` in the same response only when the user explicitly requested end-to-end ideation and delegated selection. Mark the lock before continuing.

## Creativity Failure Check

Before presenting the directions, check:

- Did I merely restate the user's idea?
- Would the user still need to invent the important mechanisms themselves?
- Are the directions structurally different?
- Is at least one direction memorable for a specific design move?
- Did I make a real recommendation rather than distribute praise evenly?
- Did I generate novelty by changing a premise or mechanism, not by piling on features?

If any answer is weak, revise before responding.

## Anti-Patterns

- Starting with a blank-page taste questionnaire.
- Listing features instead of concepts.
- Fully specifying every option before selection.
- Anchoring the whole exploration on the conventional answer.
- Presenting a reckless option as innovation without a plausible mechanism.
- Violating explicit constraints in the name of creativity.
- Making the user perform all synthesis and recommendation work.
