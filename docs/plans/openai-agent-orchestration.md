# OpenAI Agent Orchestration

## Goal

Phase 4 replaces the deterministic chat placeholder with a real, bounded OpenAI Responses API orchestration loop. A shopper can send the existing `POST /api/v1/chat` request, the model can make one or more calls to the four existing read-only commerce tools, and the API returns the model's final shopper-facing text together with an inspectable execution trace.

The observable Phase 4 boundary is intentionally narrow:

- `message` becomes real model-generated text.
- `recommendations` remains `[]` because authoritative recommendation hydration belongs to Phase 5.
- `promotion` and `pricing` remain `null`.
- One shopper turn can contain several model/tool steps, but one turn does not inherit OpenAI conversation history from earlier turns. Existing session IDs and turn indices continue to work.
- Product, price, stock, promotion, and URL facts remain authoritative only when obtained through the deterministic commerce layer.

The implementation is complete when direct-text, successful tool-loop, negative commerce-result, malformed-call, bounded-loop, and model-failure paths are deterministic under offline tests; the existing HTTP contract and all Phase 0-3 tests remain green; and an explicitly invoked live smoke check can exercise the real API without becoming a CI requirement.

## Context and authoritative sources

Repository sources, in precedence order for this work:

- `AGENTS.md` defines the commerce trust boundary, read-only tool policy, API/testability expectations, and V1 non-goals.
- `.agent/PLANS.md` defines this plan's required structure and maintenance rules.
- `contracts/salesagent_api_contract.yaml` defines `POST /api/v1/chat`, the evaluation-only trace endpoint, and all public response/trace fields.
- `data/products.json` and `data/discounts.json` remain the authoritative commerce fixtures.
- `src/salesagent/domain/models.py`, `src/salesagent/repositories/products.py`, `src/salesagent/repositories/promotions.py`, and `src/salesagent/services/commerce.py` implement deterministic commerce behavior.
- `src/salesagent/agent/tools/definitions.py` is the one authoritative OpenAI-facing tool registry. Its current descriptions are intentional and must be preserved unless a verified SDK incompatibility requires a narrowly reviewed change.
- `src/salesagent/agent/tools/dispatcher.py`, `models.py`, and `serialization.py` provide the allowlisted, schema-validated execution boundary and JSON-safe results.
- `src/salesagent/services/chat.py`, `src/salesagent/main.py`, `src/salesagent/config.py`, `src/salesagent/api/models.py`, the route factories, and `src/salesagent/repositories/traces.py` implement the current Phase 2 API shell and in-memory trace/session-turn behavior.
- The tests under `tests/` describe the observable Phase 0-3 baseline.

Implementation must also be checked against the current official OpenAI documentation rather than recalled SDK shapes:

- [Function calling](https://developers.openai.com/api/docs/guides/function-calling) defines `function_call` output items and the matching `function_call_output` input item keyed by `call_id`.
- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state) defines continuation with `previous_response_id`.
- [Create a model response](https://developers.openai.com/api/reference/resources/responses/methods/create) documents that prior `instructions` do not carry forward with `previous_response_id`, and defines `max_output_tokens`, `parallel_tool_calls`, response usage, and response status/error fields.
- [Current model guidance](https://developers.openai.com/api/docs/guides/latest-model) should be rechecked when implementation begins. As of this plan, `gpt-5.6-terra` is the intended balance of capability and cost for development and supports Responses function calling and configurable reasoning effort.

## Scope

This work includes:

- adding the official `openai` Python SDK as a bounded runtime dependency;
- environment-backed OpenAI model settings and `.env.example`/README documentation;
- a small, versioned developer instruction;
- a narrow injectable Responses API client adapter and application-owned response snapshots for offline tests;
- a synchronous, deterministic orchestration loop that supports direct text and custom function calls;
- dispatch through the existing `ToolDispatcher` only;
- per-turn response usage accumulation, total orchestration latency, ordered tool traces, and safe trace errors;
- replacing the Phase 2 stub in `ChatService` while preserving the public API, session generation, session turn counting, and trace gating;
- offline unit/integration/API tests and one optional, explicitly invoked live smoke command.

Likely files created or changed during implementation:

```text
pyproject.toml
uv.lock
.env.example
README.md
src/salesagent/config.py
src/salesagent/main.py
src/salesagent/services/chat.py
src/salesagent/agent/instructions.py                 # new
src/salesagent/agent/responses_client.py             # new
src/salesagent/agent/orchestrator.py                 # new
tests/test_config.py                                 # new or folded into API tests
tests/test_responses_client.py                       # new
tests/test_agent_orchestrator.py                     # new
tests/test_api.py
scripts/smoke_openai_agent.py                        # optional, explicit live check
docs/plans/openai-agent-orchestration.md             # kept current while executing
```

Small adjustments to `src/salesagent/api/models.py` are allowed only if needed to construct existing trace models cleanly; no public schema change is planned. The tool registry, dispatcher, and commerce modules should not require behavior changes.

## Non-goals

Phase 4 does not implement:

- structured product recommendation hydration or model-authored product cards;
- final-price or discount application;
- cross-turn model history, shopper constraint retention/replacement, or completed constraint-change tracing;
- a frontend, streaming, database persistence, the external evaluation harness, RAG, embeddings, semantic search, or web search;
- Agents SDK, Chat Completions, Assistants API, another provider, or an external agent framework;
- new tools, arbitrary Python execution, mutation tools, catalogue writes, stock changes, or promotion changes;
- exposing hidden instructions, chain-of-thought, reasoning content, credentials, raw provider exceptions, or authorization data.

`resolved_constraints` and `constraint_changes` keep their Phase 2 defaults until the later conversation-state phase. Phase 4 must not infer or persist them from prose.

## Current state

`src/salesagent/main.py:create_app` currently creates one `InMemoryTraceRepository` and one `ChatService`, includes the chat route, and conditionally includes the trace route. It performs no network work. The module-level `app` must remain importable even if `OPENAI_API_KEY` is absent.

`src/salesagent/services/chat.py:ChatService.chat` currently:

1. preserves a supplied session ID or creates a UUID;
2. creates a trace UUID and increments an in-memory, per-session turn index under a lock;
3. returns `Sales Agent is not configured yet.` with empty recommendation/pricing fields;
4. stores a trace with `model="stub"`, `prompt_version="none"`, no tools, and zero usage.

`src/salesagent/agent/tools/definitions.py:tool_definitions()` already returns fresh strict Responses-style function definitions for exactly `search_products`, `get_product`, `check_inventory`, and `validate_discount`. Those definitions are generated from the same Pydantic argument models enforced by `ToolDispatcher`. The user's recently refined descriptions spell out deterministic ordering, exact inventory statuses, discount outcomes, and the discovery-versus-selection boundary; the orchestration implementation must consume these definitions unchanged.

`ToolDispatcher.dispatch(name, arguments)` is the only execution path. It validates the allowlisted name and arguments, delegates to `CommerceService`, and returns a JSON-safe `ToolExecutionResult`. Decimal prices and percentages are already serialized as strings. A negative business outcome such as an inactive/unknown discount or unavailable variant is structured tool data and is not an infrastructure failure. Invalid arguments, unknown tools, a missing `get_product` product, and unexpected execution failures produce safe error envelopes.

The trace contract stores successful/error tool executions as an ordered list with a one-based sequence and provider `call_id`. `TraceError` can record safe non-tool failures and rejected attempts. `ToolCallTrace.tool_name` is restricted to the four known tools and its `arguments` field is described as schema-validated, so an unknown tool attempt or arguments rejected before validation cannot truthfully be represented as an executed `ToolCallTrace`; those attempts will instead be recorded as `TraceError` entries tied to `tool_call_id`.

## Proposed design

### Components and dependency direction

Keep the dependency flow concrete and OpenAI-specific:

```text
FastAPI chat route
    -> ChatService (session/turn/trace/API response owner)
        -> AgentOrchestrator (one-turn Responses loop)
            -> ResponsesClient protocol
                -> OpenAIResponsesClient (official SDK adapter)
            -> existing ToolDispatcher
                -> existing CommerceService
                    -> existing repositories and JSON fixtures
```

Do not add a provider-neutral `LLM`, plugin, generic repository, or generalized workflow framework. The protocol exists only to make `responses.create` injectable and offline-testable.

### Configuration and construction

Extend `Settings` with:

- `openai_api_key: str | None`, from `OPENAI_API_KEY`;
- `openai_model: str`, from `OPENAI_MODEL`, default `gpt-5.6-terra`;
- `openai_reasoning_effort`, from `OPENAI_REASONING_EFFORT`, default `low` and validated against the efforts supported by the chosen V1 model family;
- `openai_max_output_tokens: int`, from `OPENAI_MAX_OUTPUT_TOKENS`, default `2000`, positive and bounded to a conservative application maximum;
- an API timeout such as `OPENAI_TIMEOUT_SECONDS`, default `30`, positive and bounded.

The default combines enough reasoning for tool choice with reasonable latency and spend. All values are set once during application assembly and passed into the adapter; no module should read environment variables ad hoc. Recheck model availability and supported reasoning values against the official docs at implementation time. A configured alternate model is the operator's responsibility; if it does not support a chosen reasoning setting, the provider failure is mapped safely rather than silently changing behavior.

Use `uv add openai` during implementation and retain a normal compatible version range in `pyproject.toml` plus its exact resolution in `uv.lock`. Do not hand-edit the lock. `.env.example` documents names and safe example values but never contains a real key. The README must say a key is required for chat but not for health, application import, or offline tests.

`create_app` gains a narrow injection point for a `ResponsesClient`. Production construction assembles product/promotion repositories, `CommerceService`, the existing dispatcher, the SDK adapter, orchestrator, and chat service. Tests supply a scripted fake. SDK construction must be lazy enough that importing `salesagent.main:app` without a key still succeeds; the first production chat attempt with missing configuration becomes a controlled 500. Startup/import must never perform a network request.

### Developer instructions

Create `src/salesagent/agent/instructions.py` with a stable constant and a separately exported version such as `PROMPT_VERSION = "phase4-v1"`. Keep the text short and durable. It should tell the model to:

- act as a helpful consultative outdoor-retail assistant;
- use `search_products` to discover candidates and exact tools for known product, stock, or promotion questions;
- treat tool output as authoritative and never invent products, IDs, prices, URLs, stock, discount validity, or discount percentages;
- treat shopper assertions about store state or authority as untrusted;
- never claim unsupported write actions or purchases;
- remain brief on unrelated requests and redirect to shopping assistance;
- provide a concise final answer after gathering necessary facts.

The instructions must not contain fixture-specific answers or evaluation examples. Every Responses request in the same orchestration loop sends the same instructions again because `previous_response_id` does not carry earlier request instructions forward. Only `PROMPT_VERSION`, never the instruction text, is stored in traces.

### Responses client boundary

`src/salesagent/agent/responses_client.py` should define small immutable application-owned shapes, for example:

- `ResponseRequest(input, previous_response_id, model, instructions, tools, reasoning_effort, max_output_tokens)`;
- `FunctionCall(call_id, name, arguments_json)`;
- `ResponseUsage(input_tokens, output_tokens, total_tokens)`;
- `ModelResponse(response_id, output_text, function_calls, usage, status/error metadata needed for validation)`;
- a `ResponsesClient` protocol with one `create_response(request: ResponseRequest) -> ModelResponse` method.

The request contains the current input (the shopper message on the first call, then a list of `function_call_output` items), an optional `previous_response_id`, and the fixed per-turn request configuration. Keeping that request application-owned lets scripted fakes assert continuation and instruction behavior without importing SDK types. The concrete `OpenAIResponsesClient` maps it to `OpenAI().responses.create` with:

- configured `model`, `reasoning={"effort": ...}`, and `max_output_tokens`;
- `instructions=DEVELOPER_INSTRUCTIONS` on every call;
- `tools=tool_definitions()` on every call;
- `tool_choice="auto"`;
- `parallel_tool_calls=False` to encourage a simple one-at-a-time trajectory;
- `store=True` explicitly so `previous_response_id` can continue the within-turn response chain.

The adapter converts SDK output into application-owned snapshots immediately. It extracts every output item whose type is `function_call` in returned order, preserves the exact `call_id`, retains the arguments JSON string for orchestration validation, and maps `response.output_text` and `response.usage`. It must treat incomplete/failed responses or missing response metadata predictably. A function call with a missing `call_id` is a terminal malformed provider response because no valid correlated `function_call_output` can be constructed. Tests of this adapter use SDK-shaped local doubles to catch mapping drift without calling the network.

Explicit storage is an informed V1 trade-off: it makes the required `previous_response_id` loop simple, but OpenAI response retention and organization data controls must be reviewed before production use. If Zero Data Retention becomes a requirement, a later change should set `store=False` and manually replay all required output/reasoning items; Phase 4 must not mix that more complex strategy into the first loop.

### One-turn orchestration loop

`AgentOrchestrator.run(user_message)` returns an application-owned result containing final text, ordered tool traces, accumulated usage, safe errors, and the configured model/prompt version. It owns no session state and does not access commerce repositories directly.

Pseudocode:

```text
input = user_message
previous_response_id = null
usage = zero
tool_traces = []
errors = []
seen_call_signatures = counter

for response_number in 1..6:
    response = responses_client.create_response(
        input=input,
        previous_response_id=previous_response_id,
        same instructions, tools, and configuration on every request,
    )
    usage += response.usage
    calls = response.function_calls in output order

    if calls is empty:
        require nonblank final output_text
        return final text plus trace evidence

    require total custom calls + len(calls) <= 8
    require every call_id to be nonblank and unique within the response/turn;
        otherwise fail terminally as malformed_model_response
    function_outputs = []
    for call in calls, sequentially:
        parse call.arguments_json as one JSON object
        reject malformed/non-object input safely
        enforce repeat limit
        dispatcher_result = existing dispatcher.dispatch(call.name, arguments)
        record valid dispatched calls in sequence order
        record rejected calls as safe trace errors
        function_outputs.append({
            "type": "function_call_output",
            "call_id": call.call_id,
            "output": json.dumps(dispatcher_result, compact/deterministic),
        })

    input = function_outputs
    previous_response_id = response.response_id

fail predictably if no final text was produced by the bounds
```

The limits are:

- at most **6 Responses API calls** per shopper turn, including the initial request and final-answer request;
- at most **8 custom function calls** across those responses;
- at most **2 occurrences of an identical `(tool name, canonical JSON arguments)` signature**; a third is rejected as a repeated-call loop;
- every malformed argument payload, unknown tool attempt, and rejected repeated call counts toward the total function-call limit.

Six model iterations allow representative `search -> get -> inventory -> discount -> final` behavior with one recovery step. Eight tool calls allow a returned batch or several candidate checks without permitting runaway cost. Two identical calls allow one model correction/recheck while detecting a third repetition as non-progress. These are application-enforced constants, not prompt-only suggestions; they can become settings later only if evaluation demonstrates a need.

Although `parallel_tool_calls=False` asks the model for zero or one call per response, the parser remains defensive: if a response contains multiple custom calls, process them sequentially in the exact returned order. The tools are read-only, and sequential dispatch gives deterministic trace sequence and simple failure semantics without async complexity. All results from that batch are returned together as `function_call_output` items matching their original call IDs.

Malformed JSON or a JSON value other than an object does not reach the dispatcher. Construct the same safe `ToolExecutionResult`-shaped error payload with code `invalid_arguments`, return it to the model under the original call ID, and record a `TraceError`; do not store the raw unvalidated arguments in `ToolCallTrace`. For a parsed object, always call `ToolDispatcher`, including for an unknown name. If `result.arguments` is non-null, it is the dispatcher's validated/serialized argument mapping and the attempt can be recorded as `ToolCallTrace`. If validation failed or the tool name is unknown, record a safe `TraceError` instead, because the current trace contract permits only allowlisted names and validated arguments. The safe dispatcher envelope is still returned to the model so it can recover.

Serialize the complete `ToolExecutionResult.model_dump(mode="json")` with deterministic `json.dumps` settings. This preserves string-form Decimal money and percentages, stable error semantics, and the distinction between a successful tool execution with a negative business answer and a tool/infrastructure failure. Never send raw Pydantic objects or use float conversion for authoritative tool values.

A response with neither calls nor nonblank `output_text`, an incomplete/failed provider response, or exhaustion of either limit becomes an orchestration infrastructure failure. A missing `call_id` is immediately terminal with code `malformed_model_response` because the application cannot construct a valid `function_call_output`. A duplicate `call_id` is also immediately terminal with the same code because output correlation is ambiguous. Preflight the complete returned batch before dispatch: if IDs repeat within the batch, dispatch none of that batch; if an ID reuses one seen in an earlier response, do not dispatch the new call. In neither case should the application reuse the ID or guess which call it identifies. These ID failures are not recoverable rejected calls and no function-call output is sent. Do not return partial model prose as a successful answer when function calls are also present; execute valid calls and wait for a later final response.

### Trace and API integration

`ChatService` continues to own UUIDs, per-session turn numbers, wall-clock timestamp, top-level API construction, and trace persistence. It delegates only the one-turn model/tool run to `AgentOrchestrator`.

On success it returns:

- `message=orchestration_result.final_text`;
- `recommendations=[]`;
- `promotion=None` and `pricing=None`;
- the existing session and trace IDs.

It stores a `TraceResponse` with:

- `model` from the configured request model and `prompt_version=phase4-v1`;
- tool calls copied in actual dispatch order with contiguous one-based `sequence`, exact OpenAI `call_id`, validated arguments, the full structured dispatcher envelope as `result`, `success/error` status, and dispatcher-measured `duration_ms`;
- token usage summed field-by-field across every Responses request in the turn;
- `latency_ms` measured once around the entire `ChatService.chat` orchestration, including every provider request, local tool execution, result serialization, response assembly, and trace construction;
- safe `TraceError` entries for recoverable rejected model calls and any terminal failure;
- empty constraint/change/product-ID fields and the existing vacuously true recommendation validation until their owning phases.

Do not record raw provider request/response objects, API keys, headers, environment values, developer instructions, reasoning items, or chain-of-thought. Tool results are already intentionally structured commerce evidence; still review them for unexpected exception text.

On terminal failure, `ChatService` completes and stores a safe failure trace where possible, then raises one application exception carrying an internal trace ID and stable error category but no provider message. The chat route maps that exception to the contract's existing HTTP 500 behavior with a generic detail such as `Sales Agent is temporarily unavailable.` It must not add a new success/error response variant or expose the internal trace ID, raw OpenAI exception, request ID, credential, or prompt. Service-level tests can use the exception's trace ID to retrieve and inspect the stored failure trace; shopper-facing API tests assert only the generic response.

Classify failures into stable internal/trace codes such as `missing_openai_configuration`, `openai_authentication_failed`, `openai_invalid_request`, `openai_rate_limited`, `openai_timeout`, `openai_unavailable`, `malformed_model_response`, and `orchestration_limit_reached`. Catch documented official SDK exceptions narrowly in the concrete adapter and translate them to application errors. Configure an intentional bounded SDK timeout and retry policy; do not add an unbounded application retry loop. A dispatcher business/error envelope remains part of the model loop and is not automatically an HTTP 500.

No `previous_response_id` is stored against `session_id`. Each call to `ChatService.chat` starts with the current request message and a null previous response ID. Phase 6 will introduce cross-turn state deliberately.

## Milestones

### Milestone 1 — OpenAI configuration and client boundary

#### Outcome

The official SDK is installed, model settings are validated centrally, application import remains offline-safe without a key, and a fakeable adapter can map one Responses result into application-owned types.

#### Implementation

- Add `openai` with `uv add openai`; inspect the generated compatible version range and lock update.
- Extend `Settings` and focused configuration tests for key/model/reasoning/token/timeout values and invalid inputs.
- Add `responses_client.py` with the protocol, response snapshots, safe adapter error types, and concrete SDK adapter.
- Add adapter tests using SDK-shaped local doubles for immediate output text, function call extraction/order, response IDs/status, usage mapping, and documented provider exceptions.
- Add lazy construction/injection so `salesagent.main` imports without a key or network access.

#### Validation

- `uv run pytest tests/test_responses_client.py tests/test_config.py`
- `uv run python -c "import salesagent.main; print(salesagent.main.app.title)"` succeeds without `OPENAI_API_KEY`.
- A test spy confirms adapter construction/calls do not occur during module import.

### Milestone 2 — Versioned developer instructions

#### Outcome

Every future Responses call can use one lean instruction source and the traceable prompt version without leaking instruction text.

#### Implementation

- Add `instructions.py` with `DEVELOPER_INSTRUCTIONS` and `PROMPT_VERSION`.
- Encode only the durable behavior and trust boundaries described above.
- Pass the constant into every adapter request; do not copy it into the chat service or tests.
- Add a focused test that initial and continuation requests use the same instruction value, while traces expose only the version.

#### Validation

- Inspect the instruction for fixture/golden-case leakage.
- Targeted fake-client test proves instructions are reapplied after a `previous_response_id` continuation.

### Milestone 3 — Single-response model execution

#### Outcome

An orchestrator can turn a direct successful Responses output into final text and accumulated usage without invoking a tool.

#### Implementation

- Add `orchestrator.py` with typed success/failure results and zero-value accumulators.
- Implement the first request, direct-final response validation, and usage mapping.
- Keep the orchestrator independent of HTTP/session/trace persistence.
- Add a scripted fake `ResponsesClient` shared only by tests.

#### Validation

- Direct-final test asserts exact shopper text, no tool calls, one provider request, zero previous response ID, configured tools/instructions, and one response's usage.
- Empty output and failed/incomplete response tests assert stable safe failures.

### Milestone 4 — Function-call orchestration loop

#### Outcome

One shopper turn can perform valid one-call and multi-step commerce trajectories and return a final model answer.

#### Implementation

- Parse ordered function calls and require unique nonblank `call_id` values before dispatch. A missing or duplicate ID terminates the turn as `malformed_model_response`; it is never repaired or returned as a rejected-call output.
- Require arguments to be JSON objects. Malformed JSON/non-object arguments remain recoverable when the call has a valid unique ID: return a safe `invalid_arguments` output under that original ID.
- Dispatch parsed calls only through the existing `ToolDispatcher`.
- Serialize the complete result envelope and feed `function_call_output` items back with exact call IDs.
- Chain each continuation with the immediately preceding `response.id` and reapply instructions/tools/configuration.
- Process any multi-call batch sequentially in returned order.

#### Validation

- One-call `search_products -> final` test.
- Sequential `search_products -> check_inventory -> final` test.
- A multi-call-in-one-response test proves returned-order dispatch and batched outputs.
- Spy assertions prove exact dispatcher arguments, exact `call_id` preservation, `previous_response_id` chaining, result serialization, and no direct commerce access.
- Negative product/inventory/discount result tests prove the structured outcome is sent back rather than converted to an infrastructure failure.

### Milestone 5 — Tool trajectory trace integration

#### Outcome

Successful turns produce evaluator-useful ordered trajectories, model/prompt metadata, per-turn usage totals, and meaningful timing without leaking hidden content.

#### Implementation

- Map validated dispatcher results to `ToolCallTrace` entries at execution time.
- Aggregate all response usage fields using integer addition.
- Return trace evidence from the orchestrator and assemble/persist the contract `TraceResponse` in `ChatService`.
- Measure top-level latency across the complete turn; retain each dispatcher's tool duration.
- Preserve empty recommendations, resolved constraints, changes, promotion, and pricing.

#### Validation

- Tests assert contiguous sequence numbers, exact tool call IDs/names/validated arguments/results/statuses, and execution order.
- A three-response fake asserts accumulated input/output/total tokens equal the sum of all responses.
- Controlled timing tests assert nonnegative per-tool and total latency and that top-level latency covers the orchestration boundary without asserting fragile exact wall-clock values.
- Trace serialization tests assert no API key, authorization text, developer instruction text, raw exception, or reasoning content appears.

### Milestone 6 — Error and orchestration-limit handling

#### Outcome

Malformed calls, repeated/no-progress behavior, provider errors, missing configuration, and exhausted limits terminate predictably and safely, while recoverable tool failures can still reach a final answer.

#### Implementation

- Enforce the 6-response, 8-function-call, and two-identical-call limits.
- Add safe rejected-call outputs/errors for invalid JSON, non-object arguments, unknown tools, argument schema failures, and repeated calls. Each recoverable result must use the original valid unique `call_id`.
- Treat missing and duplicate `call_id` values as terminal `malformed_model_response` failures before dispatch. Missing IDs cannot form valid outputs, and duplicate IDs make correlation ambiguous, so neither case sends `function_call_output` items.
- Translate documented SDK authentication/rate-limit/timeout/connection/status failures to stable internal codes.
- Add the application-level failure exception, safe failure-trace persistence, and generic HTTP 500 mapping.
- Confirm timeout/retry values are bounded and documented.

#### Validation

- Recoverability tests prove malformed JSON, invalid Pydantic arguments, and unknown tools return their safe result using the original `call_id`, then allow the model to continue.
- Terminal tests prove a missing or duplicate `call_id` produces `malformed_model_response`, dispatches no ambiguous call, sends no function output, and makes no continuation request.
- Tests also cover a third identical call, maximum call count, maximum response count, and a response with no usable text/calls.
- Tests cover missing key, authentication, rate limit, timeout, and generic transient provider failure without matching raw exception text in API or trace output.
- A dispatcher `product_not_found` or unknown discount test can recover to final text and remains a 200, demonstrating business-negative versus infrastructure-failure semantics.

### Milestone 7 — Chat endpoint integration

#### Outcome

The existing endpoint returns real orchestrated prose and preserves its Phase 2 contract, session behavior, trace route gating, and intentionally empty Phase 4 structured commerce fields.

#### Implementation

- Assemble real repositories, `CommerceService`, dispatcher, Responses adapter, orchestrator, and `ChatService` in `create_app`.
- Provide an explicit fake-client injection path for API tests without exposing implementation details in routes.
- Replace the stub message path and update README/current phase language.
- Keep health and OpenAPI contracts unchanged.

#### Validation

- API tests cover omitted/null session generation, supplied session preservation, turn indices, unique trace IDs, trace retrieval/gating, direct answer, a tool loop, and generic 500.
- Assert every successful Phase 4 response has model text, `recommendations=[]`, `promotion=null`, and `pricing=null`.
- Assert no new endpoint and no contract schema/path changes.

### Milestone 8 — Offline integration tests and optional live smoke verification

#### Outcome

The full suite proves Phase 4 offline, and a developer can deliberately verify real Responses compatibility with one small paid request.

#### Implementation

- Consolidate behavior-focused fakes and remove any test that patches deep SDK internals unnecessarily.
- Add an optional script such as `scripts/smoke_openai_agent.py` that requires `OPENAI_API_KEY`, makes one bounded request through the same application orchestration path, and reports only safe response/trace summaries.
- Document that the script is manual, may incur cost, is not a pytest test, and should not print the key, hidden instructions, or raw response objects.
- Review the complete diff against the non-goals and update this plan's progress, discoveries, decisions, risks, and outcome.

#### Validation

- Run the complete validation commands below with no network access required.
- Optional only: `uv run python scripts/smoke_openai_agent.py` with a developer-supplied `OPENAI_API_KEY`; expect one successful, bounded chat response and a trace whose model/usage fields are non-stub/nonzero where reported by the API.

## Test plan

### Unit tests

- Settings parsing/defaults and missing/invalid configuration.
- SDK-to-application response mapping for text, calls, order, IDs, usage, incomplete/error statuses, and exception translation.
- Immediate final response.
- One valid function call followed by final text.
- Several sequential calls across responses and multiple calls returned together.
- Exact argument objects received by `ToolDispatcher`.
- Exact OpenAI `call_id` copied to both `function_call_output` and trace.
- Correct `previous_response_id` on every continuation and no previous ID on the first request/new shopper turn.
- Same developer instructions and `tool_definitions()` on every request.
- JSON-safe Decimal/tool-result serialization.
- Recoverable invalid JSON/non-object/Pydantic arguments and unknown tools, including output correlation to the original valid `call_id`.
- Terminal missing/duplicate `call_id` failures, including proof that no dispatch, output, or continuation occurs.
- Dispatcher failures, business-negative results, repeat detection, and both orchestration limits.
- Usage accumulation and trace ordering/status/durations.
- Provider configuration/auth/rate/timeout/transient/malformed-response failures.

### Integration and API tests

- `POST /api/v1/chat` with a fake Responses client for direct text and a commerce-backed tool loop.
- Omitted or null session ID generates a new ID; a nonempty supplied ID is preserved; empty is still rejected.
- Session turn indices remain independent and no OpenAI previous response state leaks across turns.
- The returned trace ID retrieves matching model, prompt version, tool trajectory, usage, latency, and safe errors when trace routing is enabled.
- Trace routing remains absent when disabled.
- Health, OpenAPI paths, validation limits, and all earlier commerce/tool behavior remain unchanged.
- Successful Phase 4 responses always keep structured recommendations empty and promotion/pricing null.
- Terminal orchestration/provider failures return the existing generic HTTP 500 category without a new response shape.

### Test doubles

Use one scripted `ResponsesClient` fake that accepts a queue of application-owned `ModelResponse` snapshots and records each request. It should fail a test if the orchestrator makes an unexpected extra request. Use a dispatcher spy only for focused argument/order tests; integration tests should use the real Phase 3 dispatcher and real JSON-backed commerce service. Test the concrete adapter separately with a minimal SDK-shaped fake so changes in the official response mapping are visible.

The standard pytest suite must unset/ignore real OpenAI credentials and must never instantiate a network-capable client when a fake is provided. No pytest marker should make paid calls merely by being selected accidentally.

## Security and trust-boundary checks

- The model can choose only among the four definitions returned by `tool_definitions()`. The dispatcher independently allowlists and validates every parsed call; the model cannot name a Python callable or bypass Pydantic schemas.
- Orchestration never reads `data/*.json`, calculates prices, searches products, or validates inventory/promotions. It relays dispatcher results.
- Product IDs mentioned in Phase 4 prose are model output, not trusted structured recommendations. `recommendations=[]` makes that limitation explicit until Phase 5 validates and hydrates nominated IDs.
- Prices, URLs, stock, and discounts in tool results remain deterministic. Phase 4 does not add a model-controlled path for mutating them.
- Prompt injection cannot create capabilities because only read-only tools exist. User text is sent as user input, never concatenated into developer instructions or interpreted as tool configuration.
- Traces and HTTP errors omit API keys, headers, raw SDK exceptions, hidden instructions, and reasoning items. Tests use recognizable canary secrets/instructions to prove absence.
- The evaluation trace route retains its existing environment gate. Phase 4 does not broaden its exposure or add a new observability endpoint.
- Tool payload size is bounded indirectly by the small catalogue but should still use compact JSON. If catalogue growth makes full search results too large, result pagination/projection is a later contract/tool-design change, not an orchestration shortcut.

## Validation commands

Run from the repository root after implementation:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -c "from salesagent.main import app; print(app.title)"
```

Successful validation means dependency resolution is locked; all Phase 0-4 tests pass without external network access; no lint, formatting, or strict typing errors remain; and the FastAPI application imports without requiring an API key or contacting OpenAI.

Useful targeted commands while implementing are:

```bash
uv run pytest tests/test_responses_client.py tests/test_agent_orchestrator.py
uv run pytest tests/test_api.py tests/test_tool_definitions.py tests/test_tool_dispatcher.py
```

Optional, explicit, paid verification only after all offline checks pass:

```bash
OPENAI_API_KEY=... uv run python scripts/smoke_openai_agent.py
```

The smoke command must never be run automatically and must not be considered a CI requirement.

## Progress

- [x] 2026-08-24: Inspected the Phase 1 commerce, Phase 2 API/trace, Phase 3 tool layers, tests, contract, environment, and project instructions.
- [x] 2026-08-24: Checked current official Responses function-calling, continuation/instruction, usage, and model guidance.
- [x] 2026-08-24: Authored this implementation-ready Phase 4 ExecPlan without changing application behavior or dependencies.
- [x] 2026-08-24: Milestone 1 — Added and locked OpenAI Python 3.3.1,
  centrally validated OpenAI settings, an application-owned response boundary,
  lazy SDK construction, adapter mapping tests, and offline-safe import behavior.
- [x] 2026-08-24: Milestone 2 — Added one lean, fixture-independent
  `phase4-v1` developer instruction covering consultative behavior, tool routing,
  authoritative evidence, read-only permissions, direct output, and stop rules.
- [x] 2026-08-24: Milestone 3 — Added the stateless orchestrator boundary,
  direct final-text validation, safe failed/incomplete/missing-metadata handling,
  configured request construction, and usage propagation under scripted tests.
- [x] 2026-08-24: Milestone 4 — Added exact-ID function output correlation,
  immediately preceding response continuation, ordered sequential/batched
  dispatcher execution, deterministic envelope serialization, recoverable
  malformed arguments, negative commerce evidence, and final-text completion.
- [x] 2026-08-24: Milestone 5 — Added dispatch-time tool/error evidence,
  contiguous trace mapping, field-wise usage aggregation, complete-turn latency,
  safe success/failure trace persistence, and Phase 4 response construction.
- [x] 2026-08-24: Milestone 6 — Enforced six-response, eight-call, and
  two-identical-signature bounds; terminal missing/duplicate call IDs; recoverable
  malformed/schema/unknown-tool outputs; stable SDK error translation; and safe
  failure traces plus generic HTTP error mapping under offline tests.
- [x] 2026-08-24: Milestone 7 — Assembled repositories, commerce, dispatcher,
  lazy/injectable Responses client, orchestrator, chat service, and routes;
  replaced stub HTTP behavior with offline-tested model text/tool loops while
  preserving sessions, trace gating, generic 500s, and empty Phase 4 structures.
- [x] 2026-08-24: Milestone 8 — Consolidated the scripted application-boundary
  fake, documented Phase 4 configuration/behavior/retention, added an explicit
  safe live smoke script, and completed offline integration and repository checks.
- [x] 2026-08-25: Improved the developer-only live smoke diagnostic to report
  the existing `ChatServiceError.code` category without changing the generic
  shopper HTTP 500, and added offline success, classified-failure, and
  unclassified-error redaction tests.
- [x] 2026-08-28: Replaced the OpenAI-facing `maximum_price` Decimal union with
  an explicit nullable decimal-string schema, retained Pydantic/Decimal runtime
  validation, and classified provider HTTP 400 failures as
  `openai_invalid_request` without changing the public HTTP 500.

## Discoveries

- The Phase 3 registry already emits the flat strict function schema used by the Responses API, so no duplicate or translated tool-definition registry is needed.
- The current tool descriptions were deliberately refined immediately before this plan. They already state result semantics and the discovery-versus-recommendation boundary, so Phase 4 should pass them through rather than encode those facts again in the developer prompt.
- `ToolExecutionResult.arguments` is non-null only after dispatcher argument validation. This gives the trace mapper an existing signal for whether a call can satisfy the contract's “schema-validated arguments” description.
- `ToolCallTrace.tool_name` is a four-value enum. Unknown tool attempts therefore belong in `TraceError`, not in `tool_calls`, unless the API contract is explicitly changed later.
- `ChatService` owns both trace assembly and session turn indices today. Keeping it as the HTTP application-service boundary avoids moving session concerns into the stateless orchestrator.
- Official Responses behavior requires re-sending `instructions` when continuing with `previous_response_id`; the loop must make this explicit rather than relying on prompt state.
- The repository has no current production error mapper. Phase 4 needs one narrow application exception/HTTP 500 mapping rather than a new public error schema.
- The Phase 3 `get_product` description contained an accidental trailing comma,
  making it a one-element tuple. The existing baseline test caught this and the
  installed SDK requires a string description, so implementation removed only
  that comma without changing the description text or registry structure.
- `uv add` resolved the current official SDK to `openai==3.3.1`. Its synchronous
  client accepts bounded `timeout` and `max_retries` configuration, and its
  Responses create method supports every approved Phase 4 parameter directly.
- The former `salesagent.services` package initializer eagerly imported both
  chat and commerce. Once chat depended on orchestration and orchestration on the
  commerce dispatcher, those convenience re-exports created a circular import.
  Removing unused eager re-exports restored the intended concrete-module
  dependency direction without changing a public application API.
- Live per-tool Responses validation isolated `search_products.maximum_price`
  as the only rejected strict tool field. Pydantic's validation schema for the
  nullable `Decimal` emitted a number/string/null `anyOf` with a Decimal regex;
  the Responses API accepted the other three tools but rejected that schema.
  The OpenAI-facing field now uses the supported nullable string type while the
  dispatcher still validates it through `SearchProductsArguments` into Decimal.
- The SDK's `BadRequestError` is an `APIStatusError`, so the former broad status
  catch incorrectly classified rejected HTTP 400 requests as provider
  unavailability. A preceding narrow catch now maps them to the safe
  `openai_invalid_request` category without retaining provider error text.

## Decision log

- **Decision:** Use the OpenAI Responses API, not Chat Completions or Assistants. **Reason:** It is the required current API and directly represents function-call/output trajectories. **Consequence:** The adapter handles Responses output items, IDs, usage, and continuation semantics.
- **Decision:** Own a small direct orchestration loop rather than add an agent framework. **Reason:** Four read-only tools and externally evaluated trajectories do not justify a framework. **Consequence:** Ordering, bounds, tracing, and failures remain visible in application code.
- **Decision:** Use `previous_response_id` only between Responses calls inside one shopper turn. **Reason:** It preserves model context through a tool loop without prematurely implementing Phase 6 memory. **Consequence:** Every new `/chat` request starts with no previous response ID.
- **Decision:** Re-send the same versioned developer instructions and tool definitions on every Responses request. **Reason:** Prior instructions are not carried forward by `previous_response_id`. **Consequence:** Continuation tests must inspect every recorded request.
- **Decision:** Treat missing or duplicate OpenAI function `call_id` values as terminal `malformed_model_response` failures. **Reason:** A missing ID cannot correlate a valid output, while a duplicate makes correlation ambiguous. **Consequence:** These cases are preflighted before dispatch and produce neither rejected-call outputs nor continuation requests; recoverable argument/tool errors still use their original valid unique ID.
- **Decision:** Explicitly use stored Responses for the Phase 4 continuation chain. **Reason:** This is the simplest documented `previous_response_id` path. **Consequence:** Provider retention/data controls are a production-readiness concern; ZDR would require stateless replay work.
- **Decision:** Limit a turn to 6 Responses calls, 8 custom calls, and 2 identical call signatures. **Reason:** This covers expected consultative trajectories plus one recovery while bounding latency and spend. **Consequence:** Exhaustion is a safe 500 infrastructure failure and trace error, never an infinite loop.
- **Decision:** Request `parallel_tool_calls=False` and still process any returned batch sequentially in output order. **Reason:** Read-only sequential execution is simple and trace-deterministic. **Consequence:** No async dispatcher or parallel trace reconciliation is introduced.
- **Decision:** Start with configurable `gpt-5.6-terra`, low reasoning effort, 2000 maximum output tokens, and a bounded timeout. **Reason:** Current official guidance positions Terra as a capability/cost balance, while low reasoning and a short answer ceiling suit a retail conversation baseline. **Consequence:** Evaluation may justify changing defaults through configuration without code changes.
- **Decision:** Bound configured output tokens to 16,000 and timeout to 120 seconds,
  with defaults of 2,000 and 30 seconds, and retain two SDK retries. **Reason:**
  These application limits permit operational tuning while keeping each provider
  attempt and the SDK retry behavior finite. **Consequence:** Invalid environment
  values fail during settings construction; the adapter performs no extra retry loop.
- **Decision:** Return the complete JSON-safe dispatcher envelope as function output, with Decimal-derived values preserved as strings. **Reason:** The envelope carries authoritative data and explicit negative/error semantics without a second result format. **Consequence:** The model sees stable structured evidence and no binary-float commerce values.
- **Decision:** Override only the OpenAI-facing
  `search_products.maximum_price` property with a nullable decimal-string
  schema. **Reason:** Strict Responses validation rejects Pydantic's Decimal
  `anyOf`, but changing the domain type or global schema normalization would
  weaken authoritative money handling or affect unrelated fields.
  **Consequence:** The provider emits a string or null, and the unchanged
  dispatcher/Pydantic boundary converts and validates it as `Decimal | None`.
- **Decision:** Sum input, output, and total usage from every Responses call in a shopper turn. **Reason:** The trace describes the cost of the whole observed turn, not only its final request. **Consequence:** Multi-call usage tests assert field-wise totals.
- **Decision:** Define top-level `latency_ms` as complete synchronous chat-turn orchestration latency, including provider calls and local tools. **Reason:** This matches shopper-observed service time; individual tool durations remain separately visible. **Consequence:** Tests assert containment/nonnegativity, not exact timing.
- **Decision:** Persist a safe trace and return the existing generic HTTP 500 category for terminal agent failures. **Reason:** The contract has no success-response error union, and provider details are unsafe. **Consequence:** No public shape changes; service tests inspect failure traces through an internal exception trace ID.
- **Decision:** Classify SDK `BadRequestError` separately as
  `openai_invalid_request` before the generic `APIStatusError` catch.
  **Reason:** A provider-rejected request is an integration/input failure, not
  evidence that the provider is unavailable. **Consequence:** Internal traces
  and the developer smoke diagnostic distinguish it safely, while shoppers
  still receive the same generic HTTP 500 and no provider text.
- **Decision:** Let the optional smoke script invoke the exact `ChatService`
  assembled by `create_app` and report only `ChatServiceError.code` on terminal
  failures. **Reason:** The public route deliberately discards the internal
  trace ID and category, while duplicating provider exception mapping in the
  script would create a second, potentially unsafe taxonomy. **Consequence:**
  the app retains its assembled service and trace repository in process-local
  FastAPI state for developer diagnostics; no endpoint or response shape changes.
- **Decision:** Leave recommendations empty and promotion/pricing null. **Reason:** Phase 4 model prose is not an authoritative structured commerce boundary; Phase 5 will validate and hydrate nominated products. **Consequence:** API tests explicitly prevent premature model-authored cards or prices.

## Risks and follow-ups

- **Infinite or repeated tool loops:** Enforce numeric response/call/repetition limits and count rejected attempts. Revisit values only with evaluation evidence.
- **Unnecessary tool choice and cost:** Keep instructions concise, tool descriptions precise, `parallel_tool_calls=False`, reasoning low, output bounded, and trace usage/call counts. Later prompt tuning should use evaluation results rather than fixture-specific rules.
- **Invalid arguments or unknown tools:** Parse JSON defensively, validate only through the existing dispatcher, return safe structured failures to the model, and trace rejected attempts without pretending their arguments were validated.
- **Tool-result payload growth:** Compact JSON is adequate for the current 17-product catalogue. If catalogue size grows, design explicit pagination/projection in a future tool-contract phase.
- **Prompt injection:** Treat user content as untrusted input and expose only four read-only tools. The deterministic dispatcher, not the prompt, is the security boundary.
- **Unsupported claims in final prose:** Tool grounding and lean instructions reduce risk, but Phase 4 does not parse or verify every prose claim. Phase 5 will make structured recommendations authoritative; evaluator-driven prose checks remain a follow-up.
- **Rate limits, timeouts, auth, and transient failures:** Bound SDK timeout/retries, translate documented exceptions, store safe error codes, and return generic HTTP 500 without raw details. A production availability strategy is outside V1.
- **Model aliases and behavior changes:** Keep the model configurable and trace the effective configured ID/prompt version. Consider a dated model snapshot only after evaluation demonstrates a stability need.
- **Cost:** Bound iterations/calls/output, accumulate usage, avoid automatic live tests, and document that the optional smoke check spends credits.
- **Trace correctness:** Build traces from actual dispatch results at execution time, preserve call IDs/order, and test all mappings. Do not reconstruct trajectories from final prose.
- **Hidden-instruction or secret leakage:** Never persist raw requests/responses or instruction text; add canary-based serialization tests. Provider-side response storage remains a separately reviewed data-retention risk.
- **SDK/test-double drift:** Keep the adapter small, unit-test it with SDK-shaped fixtures, recheck official docs and installed SDK types during implementation, and retain an explicit manual smoke test.
- **Failure-trace discoverability:** HTTP 500 responses intentionally do not expose trace IDs under the current contract. Failure traces are testable internally but not retrievable by a shopper without server-side correlation/logging; adding a safe correlation contract requires explicit future approval.
- **Cross-turn context:** Sessions currently preserve only turn indices. Constraint memory and prior model context remain Phase 6 work.

## Outcome

Phase 4 implementation completed on 2026-08-24. The application now uses the
official OpenAI Python SDK and Responses API behind a lazy, injectable adapter.
`AgentOrchestrator` owns a synchronous one-turn continuation loop, re-sends the
same `phase4-v1` instructions and four authoritative tool definitions on every
request, preserves exact response/call correlation, dispatches only through the
Phase 3 boundary, and enforces the six-response, eight-attempt, and
two-identical-signature limits. `ChatService` owns session turns, public response
construction, usage/latency aggregation, and safe success/failure trace storage.
Structured recommendations remain empty and promotion/pricing remain null.

OpenAI Python `3.3.1` is locked with a compatible `<4.0` range. Effective defaults
are `gpt-5.6-terra`, low reasoning, 2,000 maximum output tokens, a 30-second SDK
timeout per attempt, and two SDK retries. Settings permit bounded environment
overrides. Missing credentials do not affect import, health, or offline tests;
the first production chat fails through the safe generic HTTP 500 path.

Final validation from the repository root passed:

- `uv sync` resolved and checked the locked environment;
- `uv run pytest` passed 138 offline tests with no external OpenAI request;
- `uv run ruff check .` passed;
- `uv run ruff format --check .` passed;
- `uv run mypy src` passed in strict mode;
- `uv run python -c "from salesagent.main import app; print(app.title)"` printed
  `Sales Agent` without an API key;
- the optional smoke script's missing-key guard exited safely with status 2.

The paid live smoke check was deliberately not run. It remains an explicit
developer action documented in the README. A subsequent developer run that
failed through the generic HTTP 500 led to a narrow diagnostic improvement: the
script now calls the same assembled `ChatService`, prints its existing safe
failure category, and suppresses both classified exception causes and unexpected
exception text. The shopper-facing route still returns only the existing generic
500 detail. A later live per-tool investigation found that the Responses API
rejected only Pydantic's generated Decimal union for
`search_products.maximum_price`. The OpenAI-facing property is now explicitly a
nullable decimal string; the unchanged `SearchProductsArguments` boundary still
converts valid strings to Decimal and rejects malformed or negative values. The
same investigation established that SDK `BadRequestError` was falling through to
the generic `APIStatusError` mapping. HTTP 400 now becomes the safe internal
`openai_invalid_request` category while the public 500 remains generic.

The implementation follows the approved design. Narrow deviations were limited
to correcting the pre-existing
tuple-valued `get_product` description, removing unused eager service re-exports
that caused a circular import, and performing production dependency assembly
during trace integration so `ChatService` remained testable before final HTTP
tests. No API contract, commerce behavior, fixture, Phase 5 recommendation work,
or Phase 6 conversation memory was added.

Remaining risks are the already documented provider-side stored-Response
retention review, unvalidated model prose outside structured recommendations,
model-alias behavior drift, and failure trace discoverability under the unchanged
public 500 contract. These are follow-ups, not incomplete Phase 4 behavior.
