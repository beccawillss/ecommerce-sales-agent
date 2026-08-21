# Sales Agent

Sales Agent is the foundation for a conversational sales concierge for a fictional outdoor retailer. Phase 0 provides only a FastAPI application with a health endpoint and an automated Python development toolchain. Commerce features, AI integration, tracing, and a frontend are not implemented yet.

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

