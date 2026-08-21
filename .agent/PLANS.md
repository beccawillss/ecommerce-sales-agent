Purpose

An ExecPlan is a self-contained implementation plan for a complex Sales Agent change.

It exists so that a developer or Codex session can understand, implement, validate, and resume the work using the repository plus the plan itself, without relying on hidden conversation history.

ExecPlans are living documents. Update the plan as implementation progresses and as important discoveries or decisions are made.

When an ExecPlan is required

Use an ExecPlan for work that is complex, cross-cutting, or architecturally significant.

Examples likely to require one in this repository:

OpenAI agent orchestration and tool-call loops;

backend conversation-state management;

trace/observability architecture;

structured recommendation assembly when it crosses agent, commerce, and API layers;

a significant frontend integration;

substantial refactors affecting multiple architectural boundaries.

An ExecPlan is usually unnecessary for:

a small domain model;

one isolated commerce service;

a narrow bug fix;

a local test addition;

a documentation-only correction.

When unsure, prefer a short ExecPlan over an unstructured large change.

Where plans live

Create feature-specific plans under:

docs/plans/

Use a descriptive filename, for example:

docs/plans/openai-agent-orchestration.md

docs/plans/conversation-state.md

docs/plans/tracing.md

Do not overwrite .agent/PLANS.md; this file defines the planning format.

Plan requirements

Every ExecPlan must be understandable on its own.

Assume the reader:

has the current repository checkout;

has not seen the prior chat or task discussion;

does not know decisions that are not written in the repository or plan.

A good ExecPlan must:

describe the user-visible or evaluator-visible outcome;

identify the authoritative specifications/contracts;

explain the relevant existing architecture;

state the boundaries and non-goals;

identify files/modules expected to change;

break implementation into verifiable milestones;

state concrete validation commands and expected outcomes;

record important design decisions and discoveries;

stay updated as work progresses.

Do not write an ExecPlan that is only a checklist of files to edit.

Focus on behavior and evidence that the feature works.

Required structure

Use the following structure for new ExecPlans.

<Feature name>

Goal

Explain what capability will exist when this plan is complete and why it matters.

Describe observable behavior rather than only internal code changes.

Context and authoritative sources

List the repository files that define the requirements.

Typical examples:

AGENTS.md

docs/product-spec.md

contracts/salesagent_api_contract.yaml

relevant domain/service modules

relevant tests

Summarize any critical facts a new contributor needs to understand.

Scope

State what this work includes.

Be specific about affected layers or capabilities.

Non-goals

State what this work intentionally does not include.

Use the V1 boundaries in AGENTS.md and the product specification.

Current state

Describe how the relevant system works before the change.

Name important modules, classes, functions, routes, or data flows using repository-relative paths.

Do not assume the reader already knows them.

Proposed design

Explain the intended architecture and control flow.

For agentic changes, make trust boundaries explicit:

what the model decides;

what deterministic application code decides;

which tool/service results are authoritative;

what is validated before returning data to the shopper.

For cross-layer changes, describe the flow from request to response and trace.

Use short examples or pseudocode when they improve clarity.

Milestones

Break work into milestones that each leave the repository in a coherent, testable state.

For each milestone include:

Milestone N — <name>

Outcome

What demonstrably works after this milestone.

Implementation

Describe the changes to make, including likely files/modules.

Validation

List tests or commands that prove the milestone works.

Prefer behavior-based validation over statements such as "the class exists."

Test plan

Describe:

unit tests;

integration/API tests;

contract tests;

failure/error-path tests;

any model-adapter test doubles required.

External OpenAI calls must not be required for the default automated test suite.

Where a behavior is deterministic, prefer deterministic assertions.

Security and trust-boundary checks

For relevant features, explicitly verify:

model output cannot override authoritative commerce data;

product IDs are validated;

tool arguments are schema validated;

discount/stock/price decisions remain deterministic;

secrets are absent from traces and responses;

evaluation-only surfaces are appropriately gated.

If a category is not relevant, state why.

Validation commands

List the exact commands to run from the repository root.

Baseline:

python -m pytest
ruff check .
ruff format --check .
mypy src

Add feature-specific commands when needed.

State what successful output means, rather than pasting large expected logs.

Progress

Maintain this section while implementing.

Use dated entries or clear checkboxes.

Example:

Product tool schemas implemented and unit tested.

Tool execution loop implemented.

Integration tests for multi-call conversations passing.

Update this section whenever a milestone is completed or materially changes.

Discoveries

Record important facts learned during implementation that were not obvious when the plan began.

Examples:

an existing module already owns a responsibility the plan initially assigned elsewhere;

an SDK behavior changes the proposed orchestration loop;

a contract field requires a different internal representation.

Include why the discovery matters.

Decision log

Record material design decisions.

Use entries like:

Decision: Store trace tool calls as an ordered list rather than a mapping.

Reason: The evaluation harness must assert tool-call order.

Consequence: Each call receives an explicit sequence number.

Do not fill this section with trivial implementation details.

Risks and follow-ups

Record known limitations, deferred work, and risks that remain after V1 implementation.

Do not quietly expand scope to solve them unless they are required for the current plan.

Outcome

Complete this section at the end.

Summarize:

what was implemented;

what behavior was demonstrated;

which validation commands passed;

any deviations from the original plan and why;

remaining limitations.

The completed ExecPlan should make it possible for another contributor to understand both the intended design and what actually shipped.

Working rules while executing a plan

While implementing an ExecPlan:

Read AGENTS.md, the full ExecPlan, and its authoritative sources before making changes.

Work milestone by milestone.

Keep the plan synchronized with the implementation.

Record meaningful discoveries and decisions when they occur.

Resolve small ambiguities using repository evidence and the smallest design consistent with the contracts.

Do not silently alter the API contract, product specification, or V1 scope.

Keep the repository runnable and tests meaningful after each milestone where practical.

If the proposed design proves incorrect, update the plan before or alongside the implementation and explain the change in the decision log.

Finish by running all applicable validation commands and completing the Outcome section.