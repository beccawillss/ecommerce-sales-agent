Project purpose

Sales Agent is a V1 AI-powered e-commerce sales concierge for a fictional outdoor retailer.

The project demonstrates:

conversational product discovery and consultative selling;

OpenAI-powered agent/tool use;

deterministic commerce guardrails;

multi-turn state management;

structured product recommendations;

observability and agent traces;

compatibility with an external AI evaluation harness.

The concierge is the system under test. The separate evaluation harness must remain external to this repository.

Authoritative project sources

Before implementing behavior, read the relevant project contracts and specifications.

Treat these as authoritative when present:

docs/product-spec.md — product behavior, V1 scope, non-goals, and acceptance criteria.

contracts/salesagent_api_contract.yaml — HTTP request/response and trace schemas.

data/products.json — authoritative product facts, prices, URLs, variants, and stock.

data/discounts.json — authoritative promotion definitions.

.agent/PLANS.md — rules for writing and maintaining ExecPlans.

If code conflicts with an authoritative contract, fix the code unless the task explicitly changes the contract.

Do not silently change an authoritative contract to make an implementation easier.

Core architecture rules

The language model is not authoritative for commerce-critical facts.

The application must be the source of truth for:

product existence;

product IDs;

product attributes;

base prices;

inventory and variant availability;

discount validity and discount percentages;

calculated final prices;

product URLs.

The model may:

understand shopper intent;

ask follow-up questions;

reason conversationally;

choose tools;

nominate product IDs returned by commerce tools;

explain recommendations and trade-offs.

The model must not be trusted to invent or directly author authoritative commerce data.

Where the model nominates a product, the backend must validate the product ID and hydrate customer-facing product data from the commerce layer before returning it.

Commerce services

Keep deterministic commerce logic independent from the OpenAI integration.

Expected V1 commerce capabilities include:

search_products

get_product

check_inventory

validate_discount

Tool wrappers should delegate to commerce services rather than duplicate business logic.

All V1 commerce tools are read-only. Do not add tools that mutate prices, stock, products, promotions, baskets, or orders.

Use decimal-safe money handling. Do not use binary floating-point arithmetic for authoritative price calculations.

OpenAI integration

Keep OpenAI-specific orchestration behind a clear application boundary.

Do not embed commerce business rules only in prompts.

Prompts are behavioral guidance, not the security boundary.

Tool arguments must be schema validated before reaching commerce services.

Tool results must remain structured and authoritative.

Do not add another model provider unless a task explicitly requires it.

API and testability contract

The V1 API contract is defined in contracts/salesagent_api_contract.yaml.

Primary endpoints:

POST /api/v1/chat

GET /api/v1/traces/{trace_id}

Do not change endpoint shapes as part of an unrelated feature.

/api/v1/chat is the shopper-facing interface.

/api/v1/traces/{trace_id} is an evaluation/local interface and must be disable-able or protectable in production-style configuration.

Structured recommendations must be returned separately from free-form assistant prose.

Trace data must make agent behavior inspectable without exposing secrets.

Conversation state

Conversation state is owned by the backend.

A session must have a stable session_id.

Multi-turn behavior must support retaining, adding, and replacing relevant shopper constraints.

The trace contract must expose normalized resolved constraints and constraint changes where required by the API contract.

Do not make the frontend the sole authority for conversation state.

Evaluation boundaries

The external evaluation harness owns:

golden behavioral scenarios;

adversarial prompt datasets;

AI quality scoring;

trajectory scoring;

red-team regression runs.

This repository owns:

conventional unit tests;

integration tests;

API contract tests;

deterministic business-rule tests;

testability/trace support.

Never hard-code behavior for scenario IDs or known golden prompts.

Do not copy the golden evaluation dataset into production application logic.

The application must behave correctly for unseen paraphrases and scenarios.

V1 non-goals

Do not add the following unless a task explicitly changes V1 scope:

RAG;

embeddings;

vector databases;

semantic/vector product search;

production databases;

Shopify or other real commerce integrations;

payment processing;

real purchases;

shopping basket persistence;

shopper accounts;

refunds or returns workflows;

autonomous purchasing;

real customer data;

voice;

admin portals.

Prefer the simplest implementation that satisfies the V1 contracts.

Repository and code conventions

Use Python with FastAPI and Pydantic for the backend unless an explicit task changes the stack.

Prefer small modules with explicit responsibilities over large framework abstractions.

Keep domain/business logic separate from:

HTTP route handlers;

OpenAI orchestration;

persistence/storage adapters;

UI code.

Use type hints for public application code.

Prefer explicit data models over untyped dictionaries at application boundaries.

Avoid premature abstractions. Do not create generalized infrastructure for hypothetical future providers or databases unless current V1 behavior requires it.

Do not add production dependencies outside the task's scope. If a new dependency is necessary, explain why it is needed in the implementation summary.

Never commit secrets. Environment variables belong in .env; document required keys in .env.example.

Testing expectations

Every deterministic business rule must have automated tests.

Add or update tests in the same change as behavior.

Tests should cover success and failure paths where meaningful.

Do not mock deterministic commerce logic merely to make tests easier. Test the real domain/service behavior where practical.

External OpenAI calls must not be required for the default unit-test suite.

Use test doubles or injected adapters for model-facing unit/integration tests.

Before considering a task complete, run the applicable project checks. The expected baseline commands are:

python -m pytest
ruff check .
ruff format --check .
mypy src

If the repository later defines canonical commands in pyproject.toml, a Makefile, or task runner, use those canonical commands instead.

Report any command that could not be run and why.

Change discipline

Stay within the requested scope.

Do not refactor unrelated code while implementing a feature unless the refactor is necessary for correctness.

Do not rename public APIs, files, domain concepts, or contract fields without an explicit requirement.

Preserve backward compatibility with the current V1 contract unless the task explicitly changes that contract.

When discovering ambiguity:

inspect the product specification and API contract;

inspect existing tests and nearby implementation;

choose the smallest interpretation consistent with those sources;

record material design decisions in the ExecPlan when one exists.

Documentation

Update documentation when behavior, setup, architecture, or public interfaces change.

Keep documentation consistent with the code.

Do not claim capabilities that are not implemented and tested.

Code review rules

During implementation and self-review, flag:

any path where model-generated data can become authoritative product, price, stock, discount, or URL data;

duplicated commerce logic in prompts, routes, or tool wrappers;

hard-coded behavior for evaluation scenarios;

missing validation of tool arguments or model-selected product IDs;

money calculations performed with unsafe floating-point logic;

shopper-facing claims not grounded in authoritative commerce data;

trace endpoints exposing secrets or unnecessary hidden prompt content;

tests that pass only because they assert brittle wording instead of behavior;

changes outside the requested scope;

new dependencies without a clear V1 need.

Prefer fixing the underlying architecture over adding prompt wording that hides the defect.

Definition of done

A task is complete only when:

the requested behavior is implemented;

relevant tests are added or updated;

applicable checks pass;

API/spec contracts remain satisfied;

no unrelated scope has been introduced;

documentation is updated when needed;

the final summary states what changed, what was tested, and any known limitation.

ExecPlans

For complex features, cross-cutting work, or significant refactors, use an ExecPlan as described in .agent/PLANS.md.

An ExecPlan is normally required for work that:

spans several modules or architectural layers;

introduces a major capability such as OpenAI orchestration, conversation-state management, tracing, or a substantial frontend integration;

has meaningful design uncertainty;

will likely require multiple implementation/test iterations.

Small, isolated changes do not require an ExecPlan.