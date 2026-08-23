# Sales Agent

Sales Agent is a conversational sales concierge for a fictional outdoor retailer. Phase 3 adds four validated, read-only agent-tool adapters over the deterministic commerce layer while preserving the Phase 2 HTTP stub. AI integration, real recommendations, conversation history, pricing application, and a frontend are not implemented yet.

## Current agent-tool capabilities

The internal tool registry exposes `search_products`, `get_product`, `check_inventory`, and `validate_discount`. Calls are validated and dispatched through an explicit allowlist to the existing commerce service. Tool results use structured envelopes and serialize monetary values as exact decimal strings. These tools are not HTTP endpoints and are not invoked by the chat stub yet.

## Current API behavior

- `GET /health` reports application health.
- `POST /api/v1/chat` creates or preserves a session ID, creates a trace ID, and returns a deterministic placeholder response with no recommendations or pricing.
- `GET /api/v1/traces/{trace_id}` returns the in-memory trace for one chat turn when evaluation traces are enabled.

The stub does not invoke the commerce layer or any model. Trace and session-turn state last only for the lifetime of the application process.

## Current commerce capabilities

The application code can load and validate the fictional catalogue and promotions in `data/`, retrieve products by stable ID, filter products using typed constraints, check exact colour/size stock, and validate promotion codes. Commerce operations are application services only in Phase 1; they are not exposed as HTTP endpoints.

Search criteria are combined with AND semantics. Text and tag comparisons are case-insensitive exact matches, and results are ordered by price followed by product ID.

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)

## Setup

Install the project and development dependencies from the repository root:

```bash
uv sync
```

No runtime secrets are required. Evaluation traces are enabled by default for local development. Set `SALESAGENT_ENABLE_EVAL_TRACES=false` to remove the trace endpoint in production-style deployments.

## Run the application

Start the FastAPI development server:

```bash
uv run uvicorn salesagent.main:app --reload
```

The health and V1 API endpoints are available below `http://127.0.0.1:8000/`.

## Development checks

Run the tests:

```bash
uv run pytest
```

Check linting and formatting:

```bash
uv run ruff check .
uv run ruff format --check .
```

Run static type checking:

```bash
uv run mypy src
```
