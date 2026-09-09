# Sales Agent

Sales Agent is an AI-powered sales concierge for a fictional outdoor retailer. Phase 8 adds a plain HTML/CSS/JavaScript shopper experience served by the existing FastAPI process. Its chat uses the unchanged V1 API, and its recommendation cards, promotion status, price quote, and local product links consume only structured authoritative response fields.

The Phase 7 backend uses the OpenAI Responses API to produce a strict final object containing shopper-facing text, up to three nominated catalogue product IDs, one nullable promotion-code nomination, and explicit shopper-constraint updates after calling four validated, read-only commerce tools through a bounded application-owned orchestration loop.

The model can nominate product IDs and a promotion code, and identify explicit constraint changes. It cannot author promotion validity, percentages, product facts, or prices. Application code owns deterministic retain/set/clear merging, current-turn evidence matching, recommendation hydration, and pricing.

## Current behavior

- `GET /` serves the shopper chat UI and its same-origin static assets. The browser calls only `POST /api/v1/chat`; it never calls OpenAI or the trace endpoint directly.
- `GET /products/{slug}` resolves only exact existing authoritative `Product.url` paths and renders deterministic catalogue facts. Unknown or noncanonical paths return 404. Product pages are read-only and have no cart, checkout, payment, or purchase action.
- `GET /health` reports application health without requiring OpenAI configuration.
- `POST /api/v1/chat` starts a fresh Responses chain for the shopper turn. The backend supplies the session's normalized constraints and up to six successful historical turn pairs, then the model can call `search_products`, `get_product`, `check_inventory`, and `validate_discount` before returning strict prose, nominations, and constraint updates.
- `GET /api/v1/traces/{trace_id}` returns the in-memory turn trace when evaluation traces are enabled.

Commerce remains authoritative. The orchestration layer never reads catalogue or promotion fixtures directly: every model-selected tool name and argument object passes through the existing allowlisted, Pydantic-validated dispatcher. Tool results preserve exact decimal strings. Unknown, duplicate, and current-turn-ungrounded nominations are omitted and recorded as bounded validation evidence in the trace.

Every emitted card's canonical ID, name, Decimal price, currency, URL, and availability comes from a fresh commerce lookup. Product availability is `in_stock` when every variant has stock, `out_of_stock` when every variant is empty, and `partial` when stocked and empty variants are mixed. Phase 5 does not select an exact variant, so `matched_variant` remains `null`.

A structured promotion is returned only when its nominated code matches successful `validate_discount` evidence from the current turn. Active promotion pricing is calculated after recommendation validation and hydration, using the first accepted recommendation in its preserved final order. Earlier rejected, unknown, duplicate, or ungrounded product nominations cannot become the pricing target, and a valid promotion without an accepted recommendation has no price. The pricing service uses `Decimal`, rounds the discount amount to GBP pennies with `ROUND_HALF_UP`, then subtracts and rounds the final price. The discount amount remains internal because the V1 API contract does not expose it.

Inactive and unknown promotion codes are HTTP 200 business outcomes with `valid=false` and no pricing. Missing or ungrounded promotion selections and safe pricing-calculation failures also preserve useful cards as HTTP 200 partial results and add fixed trace error categories. Provider, malformed-output, orchestration-limit, and evidence-integrity failures retain the generic HTTP 500 boundary. Response and trace use the existing singular `pricing.product_id`; when pricing exists it equals the trace's first `recommended_product_ids` entry. Promotion evidence is never persisted as cross-turn authority, so a follow-up quote must freshly ground both its product and promotion.

One shopper turn is limited to six Responses calls, eight custom function attempts, and two occurrences of the same canonical tool-and-arguments signature. `previous_response_id` is used only inside that turn; a new `POST /api/v1/chat` starts with no OpenAI conversation state from earlier session turns. The backend instead owns complete normalized constraints and retains only the newest six successful user/assistant pairs plus IDs of cards actually returned. Failed turns consume a trace turn index but do not update constraints or history.

Session state is in memory and isolated to one application process. It is lost on restart or app recreation and is not shared across workers; production multi-worker deployment would require session affinity or separately designed shared persistence. The backend does not retain raw provider responses, reasoning, tool payloads, credentials, or cross-turn response IDs in session state.

The browser retains only the backend-returned `session_id` in `sessionStorage`; rendered messages remain in the page DOM and are not reconstructed after reload. New conversation clears that tab's transcript and stored ID but does not mutate backend state. If the backend process restarts while an ID remains in the tab, the unchanged API accepts it as a fresh session with the same ID. This is an explicit V1 limitation: the UI adds no expiry guess or hidden probe, and New conversation is the shopper's explicit reset.

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

Open `http://127.0.0.1:8000/` for the shopper UI. Health remains at `/health`, and the unchanged V1 machine endpoints remain under `/api/v1/`. Recommendation links open the catalogue-backed local `/products/...` pages in a new tab.

The continuation loop explicitly stores Responses so it can use `previous_response_id`. Review OpenAI organization data controls and retention requirements before production use. A Zero Data Retention design would require stateless replay and is outside this phase.

## Development checks

All normal checks are offline:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Optional live smoke check

After offline checks pass, a developer may explicitly run one grounded promotion-and-pricing smoke check:

```bash
OPENAI_API_KEY=... uv run python scripts/smoke_openai_agent.py
```

This command may incur OpenAI API charges. It is not a pytest test or CI requirement. It passes only when the provider accepts the exact strict Phase 7 format and bounded message context, completes its same-session constraint scenario, freshly grounds a recommendation and `WELCOME10`, and returns response/trace promotion and deterministic primary-card pricing that agree. On success it prints only safe field names, counts, canonical accepted IDs/code, validity/reason, pricing linkage checks, model/prompt version, turn indices, token totals, and latency. On a classified failure it prints the application's safe internal category, such as `openai_timeout`, while the normal shopper-facing endpoint remains a generic HTTP 500. It never prints shopper/model prose, constraint values, raw context, arithmetic inputs, keys, developer instructions, request/response bodies, reasoning, or raw provider errors.
