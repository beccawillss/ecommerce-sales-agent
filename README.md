# Sales Agent

Sales Agent is an AI-powered sales concierge for a fictional outdoor retailer. Phase 4 uses the OpenAI Responses API to produce shopper-facing text and to call four validated, read-only commerce tools through a bounded application-owned orchestration loop.

Structured recommendations intentionally remain empty in Phase 4. Product-card hydration, authoritative recommendation validation, pricing application, and cross-turn conversation memory belong to later phases.

## Current behavior

- `GET /health` reports application health without requiring OpenAI configuration.
- `POST /api/v1/chat` starts a fresh Responses chain for the shopper turn. The model can call `search_products`, `get_product`, `check_inventory`, and `validate_discount`, then return grounded prose.
- `GET /api/v1/traces/{trace_id}` returns the in-memory turn trace when evaluation traces are enabled.

Commerce remains authoritative. The orchestration layer never reads catalogue or promotion fixtures directly: every model-selected tool name and argument object passes through the existing allowlisted, Pydantic-validated dispatcher. Tool results preserve exact decimal strings. Phase 4 responses always return `recommendations=[]`, `promotion=null`, and `pricing=null`.

One shopper turn is limited to six Responses calls, eight custom function attempts, and two occurrences of the same canonical tool-and-arguments signature. `previous_response_id` is used only inside that turn; a new `POST /api/v1/chat` starts with no OpenAI conversation state from earlier session turns.

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- An OpenAI API key for live chat requests

## Setup

Install the project and development dependencies from the repository root:

```bash
uv sync
```

Copy `.env.example` values into your local environment or `.env` workflow. The application reads these variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | unset | Required when a live chat first calls OpenAI |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Responses API model ID |
| `OPENAI_REASONING_EFFORT` | `low` | One of `none`, `low`, `medium`, `high`, `xhigh`, or `max` |
| `OPENAI_MAX_OUTPUT_TOKENS` | `2000` | Per-response visible plus reasoning token ceiling; application maximum `16000` |
| `OPENAI_TIMEOUT_SECONDS` | `30` | Per-SDK-attempt timeout; application maximum `120` |
| `SALESAGENT_ENABLE_EVAL_TRACES` | `true` | Exposes or removes the evaluation trace route |

The SDK uses at most two retries. Application import, `/health`, and the complete automated test suite work without `OPENAI_API_KEY` and make no paid request.

## Run the application

Start the FastAPI development server:

```bash
uv run uvicorn salesagent.main:app --reload
```

The health and V1 API endpoints are available below `http://127.0.0.1:8000/`.

The Phase 4 continuation loop explicitly stores Responses so it can use `previous_response_id`. Review OpenAI organization data controls and retention requirements before production use. A Zero Data Retention design would require stateless replay and is outside this phase.

## Development checks

All normal checks are offline:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Optional live smoke check

After offline checks pass, a developer may explicitly run one small live chat smoke check:

```bash
OPENAI_API_KEY=... uv run python scripts/smoke_openai_agent.py
```

This command may incur OpenAI API charges. It is not a pytest test or CI requirement. On success it prints only the shopper message plus safe trace summary fields. On a classified failure it prints the application's safe internal category, such as `openai_timeout`, while the normal shopper-facing endpoint remains a generic HTTP 500. It never prints the key, developer instructions, request/response bodies, or raw provider errors.
