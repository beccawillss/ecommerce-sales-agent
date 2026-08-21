# Sales Agent

Sales Agent is a conversational sales concierge for a fictional outdoor retailer. Phase 1 provides a FastAPI health endpoint and a deterministic, JSON-backed commerce layer for product search, exact variant inventory, and promotion validation. AI integration, chat and trace APIs, pricing application, and a frontend are not implemented yet.

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

No runtime secrets or environment variables are required in Phase 0.

## Run the application

Start the FastAPI development server:

```bash
uv run uvicorn salesagent.main:app --reload
```

The health endpoint is available at `http://127.0.0.1:8000/health`.

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
