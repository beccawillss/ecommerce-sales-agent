# Structured Recommendation Nomination, Validation, and Hydration

## Goal

Phase 5 makes the existing `recommendations` field in `POST /api/v1/chat` authoritative and useful without trusting the language model to author commerce facts.

For every successful shopper turn, the model will return one strict internal final-output object containing shopper-facing prose and zero to three nominated catalogue product IDs. Application code will treat those IDs as untrusted, validate them against product IDs observed in authoritative commerce-tool results from the same turn, re-fetch accepted products through `CommerceService`, and hydrate the public `ProductRecommendation` objects from current deterministic commerce data.

The observable flow is:

```text
shopper message
    -> bounded Responses/tool loop
    -> strict final output {message, nominated_product_ids}
    -> deterministic nomination validation
    -> current catalogue lookup and availability derivation
    -> ChatResponse.message plus up to three ProductRecommendation cards
    -> trace records accepted IDs and validation evidence
```

The feature is complete when a model can nominate grounded product IDs and receive authoritative cards in the same order; unknown, duplicate, and ungrounded nominations cannot become cards; every card's name, Decimal price, currency, URL, and availability comes from deterministic application data; empty nominations remain a valid successful response; recommendation validation is accurately represented in the existing trace schema; all automated tests remain offline; and, when developer API credentials are available, one manually invoked live Phase 5 smoke check proves that the deployed model accepts the exact strict `text.format` schema and completes a grounded recommendation turn before merge.

## Context and authoritative sources

Repository sources, in precedence order for this work:

- `AGENTS.md` defines the trust boundary: the model may choose and explain product IDs returned by commerce tools, but product existence, identifiers, facts, prices, stock, and URLs remain application-authoritative.
- `.agent/PLANS.md` defines this ExecPlan's required structure and living-document rules.
- `contracts/salesagent_api_contract.yaml` defines the unchanged public `ChatResponse`, `ProductRecommendation`, `RecommendationValidation`, and `TraceResponse` shapes. `ChatResponse.recommendations` already has `maxItems: 3`.
- `data/products.json` is the source of truth for product facts, variants, stock, prices, and URLs.
- `src/salesagent/domain/models.py`, `src/salesagent/repositories/products.py`, and `src/salesagent/services/commerce.py` provide immutable Decimal-safe products, case-insensitive ID retrieval, and the deterministic commerce boundary.
- `src/salesagent/agent/tools/models.py`, `definitions.py`, `dispatcher.py`, and `serialization.py` define the four existing read-only commerce calls and their structured JSON-safe results.
- `src/salesagent/agent/responses_client.py` owns the current application-to-SDK request/response boundary. It currently requests unconstrained text and snapshots `response.output_text` plus function calls.
- `src/salesagent/agent/orchestrator.py` owns one stateless, bounded Responses chain and returns `OrchestrationResult.final_text`, tool evidence, usage, and safe errors.
- `src/salesagent/services/chat.py` currently maps `final_text` to `message`, always returns `recommendations=[]`, and stores vacuously true recommendation-validation flags with no recommended IDs.
- `src/salesagent/main.py` constructs one shared `CommerceService`, the dispatcher, orchestrator, and `ChatService`; this existing composition point can inject the same commerce authority into recommendation hydration.
- `src/salesagent/api/models.py` already matches the recommendation and trace portions of the HTTP contract, including Decimal-backed API money serialization.
- All tests under `tests/` define the Phase 1-4 baseline. In particular, client/orchestrator fakes use application-owned snapshots and all existing chat/API assertions intentionally require empty Phase 4 recommendations.
- `docs/plans/openai-agent-orchestration.md` records the completed Phase 4 design, including the six-response/eight-function-call bounds, current-turn-only Responses chains, safe terminal failures, and the explicit decision to defer recommendation hydration to Phase 5.
- `pyproject.toml`, `.env.example`, and `README.md` show that OpenAI Python `>=3.3.1,<4.0` is already the only model SDK dependency and that no new Phase 5 configuration is required.

`AGENTS.md` also identifies `docs/product-spec.md` as authoritative when present. That file is not present in the Phase 4 checkout inspected for this plan. Phase 5 therefore must use `AGENTS.md`, the API contract, catalogue fixtures, implementation, and tests as the available authority; if `docs/product-spec.md` appears before implementation, the implementer must read it and reconcile this plan before changing code.

The current official OpenAI documentation supports the proposed model-output boundary:

- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) distinguishes function calling for application tools from a strict `text.format` JSON schema for structuring the model's user-facing response, and recommends Structured Outputs over JSON mode.
- [Create a model response](https://developers.openai.com/api/reference/resources/responses/methods/create) defines the Responses `text.format`, tool, and `previous_response_id` request fields. The installed OpenAI Python 3.3.1 client exposes both `responses.create(..., text=...)` and `responses.parse(..., text_format=...)`.

The implementation should recheck the installed SDK signature and official documentation before coding. The plan deliberately keeps the existing `responses.create` adapter and sends an application-generated strict JSON schema through `text.format`; final JSON is then validated by application-owned Pydantic code. This is a smaller change than moving orchestration onto SDK-owned parsed response objects and preserves the current test-double boundary.

## Scope

This work includes:

- one strict, application-owned final model-output model containing a nonblank `message` and an ordered list of at most three `nominated_product_ids`;
- passing the strict JSON schema as Responses `text.format` on every initial and continuation request;
- parsing and Pydantic-validating the final response only after the model returns no function calls;
- updating the developer instructions and prompt version so the model nominates only product IDs established by current-turn commerce results and uses an empty list for questions or turns with no recommendation;
- retaining an internal set of product IDs grounded by successful current-turn commerce results, never by raw model arguments or prose;
- classifying internally inconsistent successful tool-result evidence with a distinct safe `invalid_tool_evidence` category rather than as malformed model output;
- a deterministic recommendation-hydration service that validates, de-duplicates, re-fetches, and maps accepted nominations while preserving nomination order;
- deterministic product-level availability derived from authoritative variants;
- mapping hydrated application results to the existing API `ProductRecommendation` model;
- populating the existing trace `recommendation_validation` and `recommended_product_ids` fields accurately;
- offline unit, integration, API, contract, and trust-boundary tests;
- one manual, potentially billable live Phase 5 smoke verification as a pre-merge acceptance check when developer credentials are available, never as part of pytest or CI;
- updating `README.md` to describe Phase 5 behavior.

Likely files created or changed during Phase 5 implementation are:

```text
README.md
src/salesagent/agent/final_output.py                  # new strict internal output model/schema
src/salesagent/agent/instructions.py
src/salesagent/agent/responses_client.py
src/salesagent/agent/orchestrator.py
src/salesagent/services/recommendations.py            # new deterministic validator/hydrator
src/salesagent/services/chat.py
src/salesagent/main.py
scripts/smoke_openai_agent.py
tests/fakes.py                                        # only if final-output fixtures benefit from a helper
tests/test_instructions.py
tests/test_responses_client.py
tests/test_agent_orchestrator.py
tests/test_recommendations.py                         # new
tests/test_chat_service.py
tests/test_api.py
tests/test_smoke_openai_agent.py                      # only if safe success output assertions change
docs/plans/recommendation-hydration.md                # kept current during execution
```

`src/salesagent/api/models.py` and the YAML contract should not need schema changes. A narrow internal mapping helper may be added without changing any public field if implementation shows it improves type safety.

## Non-goals

Phase 5 does not include:

- changing `POST /api/v1/chat`, `GET /api/v1/traces/{trace_id}`, or any public schema;
- allowing the model to author names, prices, currency, URLs, availability, stock counts, or matched variants;
- adding a fifth nomination tool or changing the four commerce-tool contracts;
- accepting a product merely because its ID appears in user text, model prose, or raw tool arguments;
- deterministic ranking or reranking of search results; the model chooses among grounded candidates and the application preserves its nomination order;
- discount application, final-price calculation, populated `promotion`, or populated `pricing`; both fields remain `null` in chat responses and traces;
- cross-turn Responses history, conversation-state persistence, resolved-constraint extraction, or constraint-change tracking; those remain a later phase;
- exact variant selection. Phase 5 nominations contain product IDs only, so `matched_variant` remains `null`; later constraint/variant work can add an explicit authoritative rule without guessing from prose;
- validating every factual claim in free-form `message`. Structured cards become authoritative, but the Phase 4 risk of an unsupported prose claim is not silently solved by this phase;
- frontend work, databases, RAG, embeddings, new model providers, external evaluation datasets, or commerce mutations;
- new dependencies or environment settings.

## Current state

`OpenAIResponsesClient.create_response` maps an application-owned `ResponseRequest` to `client.responses.create`. It always provides the configured model, instructions, four tools, reasoning effort, output-token limit, `tool_choice="auto"`, `parallel_tool_calls=False`, `store=True`, and optional `previous_response_id`. It does not currently provide a `text` format. Its `ModelResponse` snapshot contains raw `output_text`, ordered function calls, usage, status, and incomplete metadata.

`AgentOrchestrator.run` sends the shopper message, executes schema-validated tool calls only through `ToolDispatcher`, returns correlated function outputs, and accepts the first completed response with no function calls and nonblank text. It does not parse a final object or retain which product IDs were authoritatively observed. `OrchestrationResult` therefore has only `final_text` rather than separate final prose and nominations.

Tool outputs already contain the evidence Phase 5 needs:

- successful `search_products` data contains an ordered `products` list with canonical `product_id` values and complete authoritative product facts;
- successful `get_product` data contains one canonical `product_id`;
- successful `check_inventory` data contains a canonical product ID and an explicit status; any status other than `product_not_found` proves that the product existed for that check;
- `validate_discount` contains no product evidence;
- failed/rejected calls and a `check_inventory` result with `product_not_found` do not ground a recommendation.

`ChatService.chat` currently returns model text with `recommendations=[]`, `promotion=None`, and `pricing=None`. Its trace contains the actual tool trajectory, but `recommended_product_ids=[]` and a `RecommendationValidation` whose four booleans are all `True`. That validation is intentionally vacuous only while no cards can be emitted.

`ProductRepository.get` already strips and compares IDs case-insensitively, then returns the canonical `Product`. Every valid `Product` has at least one immutable variant with a nonnegative stock count. This makes product-level availability deterministic without another model call or binary floating-point calculation.

The contract leaves two Phase 5 semantics unspecified rather than contradictory:

- it permits `availability` values `in_stock`, `out_of_stock`, `partial`, and `unknown` but does not define product-level aggregation;
- it provides four validation booleans plus free-form `validation_errors`, but no dedicated boolean for current-turn grounding or duplicate nominations.

The proposed design below resolves those ambiguities without altering the contract and records the choices in the decision log.

## Proposed design

### Strict final model output

Add an internal Pydantic model, separate from public API and commerce models:

```text
AgentFinalOutput
    message: nonblank string
    nominated_product_ids: ordered array of 0..3 nonblank strings
    extra fields: forbidden
```

The schema must require both fields, set `additionalProperties: false`, and set `maxItems: 3`. Do not include product-card fields in this schema. In particular, there is no model-provided price, URL, name, stock, availability, or variant field that application code could accidentally trust.

Add the generated strict format to `ResponseRequest` and pass it as `text={"format": ...}` in `OpenAIResponsesClient`. Use the same schema on every request in the loop, just as Phase 4 reapplies instructions and tools on every continuation. Keep SDK objects out of the orchestrator and tests.

When a completed response contains function calls, ignore any accompanying text as Phase 4 does and continue the loop. When a completed response contains no function calls, parse `output_text` with `AgentFinalOutput.model_validate_json`. Invalid JSON, wrong fields/types, extra fields, a blank message, or more than three nominations becomes the existing terminal `malformed_model_response` path, with safe failure tracing and the unchanged generic HTTP 500. A valid empty nomination list is a successful result.

Update `OrchestrationResult` to expose `final_text`, `nominated_product_ids`, and `grounded_product_ids`. The latter is application-derived evidence, not another model field.

### Prompt guidance and grounding evidence

Bump `PROMPT_VERSION` from `phase4-v1` to `phase5-v1`. Extend the lean developer instructions to state that the final structured output must:

- put shopper-facing prose in `message`;
- nominate no more than three product IDs;
- nominate only IDs returned by authoritative commerce tools during the current turn;
- use `[]` when asking a follow-up question, when no suitable product was found, or when the turn is informational rather than recommendational;
- never place product facts in the nominations beyond the ID.

The prompt improves behavior but is not the enforcement boundary.

During actual dispatch, the orchestrator derives a case-insensitive set of grounded canonical product IDs from validated `ToolExecutionResult` data:

- collect every product ID in a successful `search_products` result;
- collect the product ID in a successful `get_product` result;
- collect the product ID in a successful `check_inventory` result only when its status is not `product_not_found`;
- collect nothing from tool arguments, rejected/failed calls, unknown product results, discount results, or final prose.

Use the existing typed tool-result models to validate/extract this evidence rather than walking arbitrary dictionaries unchecked. If an internally inconsistent successful tool envelope cannot be interpreted, fail closed with a distinct safe `invalid_tool_evidence` orchestration category; do not weaken grounding or guess. Reserve `malformed_model_response` exclusively for malformed or schema-invalid provider/model output. Extend the internal orchestration/chat failure mappings so `invalid_tool_evidence` is stored as a safe trace error while the shopper still receives the existing generic HTTP 500 response. Never include the invalid payload, raw exception, or internal validation detail in the trace or HTTP response.

Grounding is limited to one `AgentOrchestrator.run` invocation. Phase 5 must not reuse IDs from earlier requests sharing the same `session_id`, because Phase 4 deliberately starts each shopper turn without model history and Phase 6 owns cross-turn state.

### Deterministic nomination validation and hydration

Create a small `RecommendationHydrator` in `src/salesagent/services/recommendations.py`. It depends on `CommerceService`, not on repositories, JSON fixtures, the OpenAI client, or HTTP routes. Its input is the model-nominated IDs plus the application-derived grounded-ID set. Its output is an immutable application result containing hydrated recommendations, accepted canonical IDs, the four contract validation booleans, and safe validation-error strings. `ChatService` remains responsible for mapping that result into HTTP and trace Pydantic models.

For each nomination in model order:

1. Strip boundary whitespace and compare IDs case-insensitively. The strict final-output model rejects blank values before this service.
2. If the normalized ID has already appeared, omit the duplicate and append a bounded error such as `duplicate_product_id:<display-id>`. The first occurrence continues through normal validation.
3. Call `CommerceService.get_product`. If it returns `None`, omit the nomination, set `all_products_exist=False`, and append `unknown_product_id:<display-id>`.
4. Compare the returned canonical product ID with the current-turn grounded set. If it was not grounded, omit it and append `ungrounded_product_id:<display-id>`. Do not treat mere catalogue existence as sufficient authorization for model selection.
5. Hydrate one internal recommendation from the freshly fetched `Product`. Never copy product facts from final model output or even from the earlier tool trace; the re-fetch makes the current commerce layer authoritative at response assembly time.

Accept at most three unique valid nominations and preserve their order. The strict model schema already caps input at three, but the hydrator should defend its public method invariant so direct unit calls cannot bypass the limit.

Define one application-side display sanitizer for every rejected nomination ID interpolated into `recommendation_validation.validation_errors`. It must strip boundary whitespace, replace control characters with a safe visible placeholder, collapse remaining whitespace runs to one space, and cap the complete displayed ID to **64 Unicode code points**. If truncation is needed, include an ellipsis within that 64-character cap. Apply this helper to duplicate, unknown, and ungrounded error strings, including canonical catalogue IDs used in rejected cases. Recommendation validation must persist only this display form and must not add a raw-nomination field or list to the trace; existing tool-call trace semantics remain unchanged. This trace bound is enforced after Structured Outputs parsing and does not require adding a potentially unsupported per-string constraint to the OpenAI-facing schema.

Nomination validation failures are recommendation evidence, not infrastructure failures. A structurally valid turn returns HTTP 200 with the model's message and only the accepted subset of cards. If every nomination is rejected, `recommendations=[]`. Record failures only in `recommendation_validation.validation_errors`; do not duplicate them into the top-level trace `errors`, which currently describes rejected tool/model and terminal orchestration failures.

### Authoritative card mapping and availability

For every accepted product, map:

- `product_id` from `Product.id`;
- `name` from `Product.name`;
- `price` directly from `Product.price` as `Decimal` until the existing API serializer emits a JSON number;
- `currency` from `Product.currency`;
- `product_url` from `Product.product_url`;
- `availability` from current `Product.variants` using the deterministic rule below;
- `matched_variant=None` because the Phase 5 nomination schema does not select a colour/size pair.

Product-level availability is:

```text
all variant stock counts > 0     -> in_stock
all variant stock counts == 0    -> out_of_stock
some positive and some zero      -> partial
no authoritative variant data    -> unknown
```

The current `Product` model requires at least one variant and nonnegative integer stock, so `unknown` is unreachable for valid Phase 5 catalogue data. Retain the branch or an exhaustive helper for forward compatibility with the public enum, but do not use `unknown` to hide malformed authoritative data.

No arithmetic is required for Phase 5. In particular, do not convert prices to binary floats within commerce or hydration code and do not calculate discounted prices.

### Trace and API integration

`ChatService` receives the same `RecommendationHydrator` assembled from the existing shared `CommerceService` in `create_app`. On orchestration success it hydrates before constructing either the response or trace.

The public response uses:

- `message=AgentFinalOutput.message`;
- `recommendations` mapped from accepted hydrated products;
- `promotion=None` and `pricing=None`.

The trace uses:

- `recommended_product_ids` equal to the canonical product IDs in the emitted response cards, in exactly the same order;
- `all_products_exist=False` if at least one unique nomination did not exist, otherwise `True`, including the empty-list case;
- `prices_match_catalogue=True` for emitted cards because price is copied from the re-fetched product and no model price is accepted;
- `urls_match_catalogue=True` for the same reason;
- `stock_claims_validated=True` for emitted cards because availability is calculated from authoritative variants and no model stock claim enters a card;
- `validation_errors` containing stable duplicate, unknown, and ungrounded-nomination codes in encounter order, with every displayed rejected ID sanitized and capped to 64 Unicode code points as defined above.

If an unexpected internal mapping defect ever prevents an authoritative field from being verified, omit the affected card and set the relevant boolean to `False` with a safe validation error rather than returning a partially model-authored card. Tests should make such a path explicit if the implementation introduces one.

Failure traces produced before a valid final output or before hydration keep `recommended_product_ids=[]` and a vacuously true empty recommendation validation, because no nominations were accepted or cards returned. Existing tool traces, token usage, latency, trace gating, and safe error behavior otherwise remain unchanged.

### Dependency direction

The intended Phase 5 dependency flow is:

```text
FastAPI chat route
    -> ChatService
        -> AgentOrchestrator
            -> ResponsesClient
            -> ToolDispatcher -> CommerceService
        -> RecommendationHydrator -> same CommerceService
        -> API response and trace mapping
```

The hydrator must not read tool arguments or catalogue fixtures directly. The orchestrator must not hydrate API cards. The route must not contain recommendation logic. This keeps model I/O, commerce validation, application assembly, and HTTP serialization as separate boundaries.

## Milestones

### Milestone 1 — Define the strict internal final-output contract

#### Outcome

The repository has one reusable, provider-independent Pydantic model and strict JSON schema for final shopper prose plus zero to three nominated IDs, without changing runtime behavior yet.

#### Implementation

- Add `src/salesagent/agent/final_output.py` with `AgentFinalOutput` and a fresh JSON-format/schema factory suitable for Responses `text.format`.
- Require both fields, forbid extras, reject blank messages and IDs, and cap nominations at three.
- Keep the internal name `nominated_product_ids` distinct from public `recommended_product_ids` so the trust boundary is visible in code.
- Add focused tests, either in a new test file or `test_agent_orchestrator.py`, for valid empty/three-ID payloads and invalid blank, extra-field, wrong-type, and over-limit payloads.

#### Validation

- `uv run pytest tests/test_agent_orchestrator.py -k "final_output or nomination"`
- A schema assertion proves `required` contains both fields, `additionalProperties` is false, and the nomination array has `maxItems: 3`.

### Milestone 2 — Carry structured final output through the Responses loop

#### Outcome

Direct and tool-loop model turns end in a validated `message` plus untrusted nominations, while all Phase 4 bounds and safe failure semantics still work.

#### Implementation

- Extend `ResponseRequest` with the application-owned strict text format and map it to the SDK `text` argument in `OpenAIResponsesClient`.
- Reapply the format on every continuation request.
- Parse final no-tool `output_text` into `AgentFinalOutput` in `AgentOrchestrator` and expose nominations separately from prose.
- Bump/update developer instructions to `phase5-v1`.
- Accumulate grounded canonical product IDs from typed successful tool results as described above.
- Add `invalid_tool_evidence` to the safe internal orchestration failure taxonomy and terminal trace-message mapping. Keep `malformed_model_response` only for invalid provider/model output and retain the existing generic shopper-facing HTTP 500.
- Preserve the exact six-response, eight-call, repeated-signature, call-ID, error, usage, and within-turn `previous_response_id` behavior.
- Update scripted response fixtures to return strict JSON final text. Do not make the fake parse or hydrate on behalf of production code.

#### Validation

- `uv run pytest tests/test_responses_client.py tests/test_agent_orchestrator.py tests/test_instructions.py`
- Adapter tests assert the exact SDK `text.format` mapping for initial and continuation requests.
- Orchestrator tests cover direct empty nominations, `search_products` nominations, `get_product` nominations, qualifying/nonqualifying `check_inventory` evidence, malformed final JSON, schema-invalid output, and a nomination never inferred from raw arguments.
- A deliberately inconsistent successful `ToolExecutionResult` produces `invalid_tool_evidence`, preserves only safe trace details, and is never reported as `malformed_model_response`; an API/service assertion confirms the public response remains the existing generic HTTP 500.
- Existing malformed tool-call and orchestration-limit cases still produce the same safe categories.

### Milestone 3 — Implement deterministic validation and hydration

#### Outcome

A model nomination list can be converted into zero to three authoritative internal recommendations with deterministic validation evidence, independently of OpenAI and HTTP.

#### Implementation

- Add `src/salesagent/services/recommendations.py` with immutable result/evidence types and `RecommendationHydrator`.
- Inject `CommerceService`; use `get_product` for every first-seen nomination.
- Implement case-insensitive duplicate handling, existence validation, current-turn grounding enforcement, canonical ID output, order preservation, and the hard three-card invariant.
- Derive product-level availability from variants.
- Preserve Decimal price values and return domain/application values for later API mapping.
- Use one application-side rejected-ID display sanitizer with the fixed 64-code-point cap, and never include full oversized IDs, exceptions, prompts, or raw provider objects.

#### Validation

- `uv run pytest tests/test_recommendations.py`
- Tests use real `ProductRepository`, `CommerceService`, and catalogue fixtures for: empty input; one and three accepted products; canonicalization; mixed valid/unknown/ungrounded IDs; case-insensitive duplicates; over-limit direct calls; in-stock (`JKT-003`), out-of-stock (`JKT-002`), and partial (`JKT-001`) availability; Decimal preservation; and `matched_variant` absence at the mapping boundary.
- Rejected-ID tests cover duplicate, unknown, and ungrounded values containing more than 64 characters, newlines/tabs, and other control characters; each trace validation string is safe, single-line, and contains no more than 64 displayed ID code points.
- A spy/test double proves accepted cards are re-fetched through `CommerceService` and not assembled from model or trace facts.

### Milestone 4 — Integrate hydrated recommendations into chat responses and traces

#### Outcome

`POST /api/v1/chat` returns authoritative cards, and its retrievable trace accurately links emitted cards to accepted canonical IDs and nomination-validation outcomes.

#### Implementation

- Inject one hydrator backed by the already assembled `CommerceService` into `ChatService` in `create_app`.
- Hydrate after successful orchestration and before response/trace construction.
- Add a narrow mapper from internal hydrated recommendations to existing `ProductRecommendation` objects.
- Populate `recommendations`, `recommended_product_ids`, and `recommendation_validation`; keep promotion/pricing and constraint fields unchanged.
- Preserve failure-trace persistence and generic HTTP 500 behavior.

#### Validation

- `uv run pytest tests/test_chat_service.py tests/test_api.py`
- Service tests assert response/trace ID order equality, exact catalogue facts, numeric JSON prices, all three availability states, empty nominations, partial acceptance, and safe validation errors.
- API tests assert no model-supplied fake price/URL/name/stock can appear, even when a fake final output nominates a real ID.
- Existing session IDs, turn indices, trace IDs, trace gating, token aggregation, tool ordering, and generic failure responses remain unchanged.

### Milestone 5 — Documentation, contract comparison, and full regression

#### Outcome

The repository documents Phase 5 accurately, public schemas remain unchanged, the complete offline quality gate passes, and one manually invoked live Structured Outputs recommendation turn passes before merge whenever developer API credentials are available.

#### Implementation

- Update `README.md` from Phase 4 empty-card language to the implemented nomination/validation/hydration behavior and its limitations.
- Compare generated FastAPI OpenAPI recommendation/trace schemas with `contracts/salesagent_api_contract.yaml`; change implementation models if they conflict, not the YAML contract.
- Update `scripts/smoke_openai_agent.py` to exercise a clear catalogue recommendation that requires commerce-tool grounding and the Phase 5 strict final schema. The script must fail unless it observes a successful turn with at least one authoritative recommendation and matching accepted trace ID, and it must print only safe summary fields such as model ID, tool-call count, recommendation count/canonical IDs, token total, latency, and safe failure category. Do not print `response.message`, the shopper prompt, instructions, raw provider responses, reasoning, exception text, credentials, or headers.
- Update this ExecPlan's Progress, Discoveries, Decision log, and Outcome with actual implementation evidence and any narrow deviations.
- Confirm no dependency, lockfile, environment variable, fixture, or unrelated source change was introduced.

#### Validation

- Run all commands under Validation commands below.
- Inspect `git diff --stat` and `git diff --check`.
- Confirm pytest and CI never invoke the live smoke or require an API key.
- When developer API credentials are available, manually run the live Phase 5 smoke as a pre-merge acceptance check and record its pass/fail result in Outcome. If credentials are unavailable, record that the conditional check could not be run rather than claiming it passed.

## Test plan

### Unit tests

- Strict final-output model/schema accepts only a nonblank message and zero to three nonblank string nominations.
- Responses adapter forwards the strict text format on every request and retains the current SDK settings.
- Orchestrator parses structured finals, separates prose from nominations, derives current-turn grounding only from typed successful tool data, and preserves all Phase 4 loop/error behavior.
- Recommendation hydrator covers empty, accepted, duplicate, unknown, ungrounded, canonicalized, mixed, and over-limit inputs.
- Availability aggregation covers all-positive, all-zero, and mixed variant stock.
- Hydration preserves `Decimal` and never accepts model-authored card fields.

### Integration and API tests

- Direct follow-up-question output with `nominated_product_ids=[]` returns a normal response and vacuously true validation.
- `search_products -> structured final` returns one to three cards in nominated order even when search result order differs.
- An accepted lowercase nomination returns the catalogue's canonical ID.
- A structured final containing accepted and rejected IDs returns only accepted cards and records validation evidence without becoming HTTP 500.
- An existing but current-turn-ungrounded product is rejected.
- A nonexistent product is rejected and makes `all_products_exist=False`.
- Every response card's ID, name, price, currency, URL, availability, and null matched variant match current commerce data.
- Trace `recommended_product_ids` exactly equals response card IDs and does not contain rejected nominations.
- `recommendations` never exceeds three; `promotion` and `pricing` remain null.
- Trace route gating, session-turn behavior, token usage, latency, and tool sequences regressions remain covered.
- Generated OpenAPI continues to expose contract-compatible numeric money and the existing recommendation fields.

### Failure and error paths

- Invalid JSON, missing fields, extra fields, blank message, wrong nomination types, and too many nominations become safe `malformed_model_response` terminal failures.
- Inconsistent successful tool-result evidence cannot expand the grounded-ID set and terminates with `invalid_tool_evidence`, never `malformed_model_response`; the trace and HTTP response contain no raw validation or exception detail.
- Recommendation re-fetch failure rejects a card and records safe validation evidence without leaking repository exceptions.
- Recommendation validation failures stay out of top-level trace `errors`; genuine orchestration/provider failures keep their existing safe handling.
- Oversized or control-character-bearing rejected IDs cannot create multiline or unbounded `recommendation_validation.validation_errors` entries.

### Test doubles

Use `ScriptedResponsesClient` and application-owned `ModelResponse` snapshots for orchestration and API tests. Final fake `output_text` values should be JSON generated from small helpers or `AgentFinalOutput`, not brittle hand-built strings where avoidable. Use the real dispatcher, real commerce service, and real fixtures for grounding/hydration integration tests. External OpenAI requests must not be part of pytest, CI, or any default automated validation command. The separately invoked live smoke is acceptance evidence for provider/schema compatibility, not an automated test.

## Security and trust-boundary checks

- **Model output cannot override commerce data:** The final schema contains only prose and IDs. All card facts come from a fresh `CommerceService.get_product` result.
- **Product IDs are validated:** Every first-seen nomination must exist and must be in the current-turn grounded-ID set before acceptance. Case normalization returns only the catalogue's canonical ID.
- **Tool arguments remain schema validated:** The existing `ToolDispatcher` stays the only execution route; Phase 5 does not bypass or duplicate it.
- **Stock remains deterministic:** Product-level availability is derived from authoritative variant stock. The model cannot supply availability or `matched_variant`.
- **Prices and URLs remain deterministic:** Decimal price and URL are copied from the re-fetched immutable `Product`; no float arithmetic, prose parsing, or trace-copying is authoritative.
- **Discount behavior is unchanged:** Promotion/pricing fields remain null and no discount is calculated.
- **Prompt injection cannot widen capability:** User/model text cannot add tools, bypass grounding, or become a card field. The four existing tools remain read-only.
- **Tool-evidence failures remain correctly classified:** Invalid provider/model output uses `malformed_model_response`; inconsistent successful application tool evidence uses `invalid_tool_evidence`. Both remain safe internal trace categories behind the unchanged generic public 500, with no raw payload or exception detail.
- **Trace content remains safe:** Persist accepted canonical IDs and bounded validation codes, not raw SDK objects, instructions, reasoning, credentials, headers, or exception text. Every rejected ID displayed in a validation error passes through the application-side sanitizer and 64-code-point cap; the OpenAI-facing schema need not enforce this trace-specific bound.
- **Evaluation-only access remains gated:** Phase 5 does not alter `SALESAGENT_ENABLE_EVAL_TRACES` or the conditional trace route.
- **No golden-case behavior:** Tests may use catalogue anchors to prove deterministic mapping, but production code must not special-case IDs, prompt wording, or evaluation scenarios.

## Validation commands

Run from the repository root:

```bash
uv run pytest tests/test_responses_client.py tests/test_agent_orchestrator.py tests/test_recommendations.py tests/test_chat_service.py tests/test_api.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -c "from salesagent.main import app; print(app.title)"
git diff --check
```

Successful output means all automated tests run without an external OpenAI request; lint, formatting, and strict type checks pass; application import still succeeds without `OPENAI_API_KEY`; the app title remains `Sales Agent`; and the diff contains no whitespace errors. These commands are the mandatory offline quality gate and are safe for pytest/CI.

When developer API credentials are available, the following separate, manually invoked, potentially billable live smoke is also a pre-merge acceptance check:

```bash
OPENAI_API_KEY=... uv run python scripts/smoke_openai_agent.py
```

The command must not be invoked by pytest or CI. It passes only when the exact Phase 5 strict `text.format` is accepted by the provider and the assembled application completes a grounded recommendation turn with at least one authoritative card whose ID matches the trace. Record the result in Outcome. The script must never print the shopper prompt, model prose, API key, instructions, raw requests/responses, reasoning, headers, exception text, or provider errors. If developer credentials are unavailable, record the conditional check as not run for that reason.

## Progress

- [x] 2026-08-29: Planning sources, Phase 1-4 implementation, all existing tests, installed OpenAI SDK boundary, and current official Structured Outputs guidance inspected.
- [x] 2026-08-29: Initial Phase 5 design and implementation milestones documented; no runtime implementation performed.
- [x] 2026-08-31: Approved pre-implementation amendments added for conditional live Structured Outputs acceptance, distinct invalid tool-evidence classification, and bounded rejected-ID trace display; no runtime implementation performed.
- [ ] Milestone 1 — Strict internal final-output contract implemented and tested.
- [ ] Milestone 2 — Structured Responses loop, prompt version, and grounding evidence implemented and tested.
- [ ] Milestone 3 — Deterministic recommendation validation/hydration implemented and tested.
- [ ] Milestone 4 — Chat response and trace integration implemented and tested.
- [ ] Milestone 5 — Documentation, contract comparison, and full regression completed.

## Discoveries

- `docs/product-spec.md` is named as authoritative by `AGENTS.md` but is absent from the inspected checkout. This matters because no unavailable product-spec semantics can be assumed for availability or matched variants; the plan uses the existing contract and records explicit decisions instead.
- The public API and trace models already contain all Phase 5 output fields. This matters because implementation should populate existing fields rather than alter the contract.
- Phase 4's adapter snapshots raw `output_text` and deliberately isolates SDK objects. OpenAI Python 3.3.1 and current official docs support strict Responses `text.format`, so Phase 5 can preserve that boundary and validate JSON with application-owned Pydantic models.
- `search_products` returns complete product facts, but hydration must still re-fetch accepted IDs. This matters because tool output is evidence for grounding while `CommerceService` remains the final response-time authority.
- `check_inventory` is a successful structured tool result even for `product_not_found` and `variant_not_found`. This matters because only statuses proving product existence may ground an ID; dispatcher `success=True` alone is insufficient.
- The catalogue domain guarantees at least one variant and nonnegative integer stock. This makes `in_stock`, `out_of_stock`, and `partial` fully deterministic; `unknown` is not needed for valid current data.
- Existing Phase 4 tests assert empty recommendations throughout API/chat integration. They must be updated deliberately while retaining empty-list cases for nonrecommendational turns and failures.

## Decision log

- **Decision:** Use a strict final Responses `text.format` with `message` and `nominated_product_ids`, not a fifth function tool. **Reason:** Function calls remain the bridge to application data, while Structured Outputs are the documented mechanism for shaping the model's final user response; a fifth tool would also conflict with the current four-tool registry and trace enum. **Consequence:** The existing loop remains intact and the final output gains one explicit schema-validation boundary.
- **Decision:** Keep using `responses.create` plus application-owned Pydantic parsing rather than switching the adapter to SDK `responses.parse`. **Reason:** The current architecture snapshots SDK results immediately and uses provider-independent fakes. **Consequence:** The adapter sends the strict schema, while the orchestrator owns final semantic validation and safe error mapping.
- **Decision:** Require one manual live Phase 5 smoke before merge when developer credentials are available, while keeping all automated tests offline. **Reason:** Phase 4 encountered a provider-side schema compatibility defect that SDK-shaped offline tests did not reveal, and Phase 5 introduces a new strict `text.format`. **Consequence:** Provider/schema compatibility receives explicit live acceptance evidence without adding paid, credential-dependent, or nondeterministic calls to pytest or CI.
- **Decision:** Classify inconsistent successful tool evidence as `invalid_tool_evidence`, not `malformed_model_response`. **Reason:** The former is an internal application/tool-boundary integrity failure, while the latter must identify invalid provider/model output. **Consequence:** Internal traces retain useful safe taxonomy, and both failure types continue to produce the same generic shopper-facing HTTP 500.
- **Decision:** Permit only current-turn tool-grounded nominations. **Reason:** `AGENTS.md` allows the model to nominate IDs returned by commerce tools, and prompts alone are not a security boundary. **Consequence:** An existing catalogue ID guessed by the model is still rejected unless this turn established it through authoritative tool data.
- **Decision:** Re-fetch accepted IDs through `CommerceService` rather than hydrate from tool traces. **Reason:** The commerce service is the application source of truth at response assembly time. **Consequence:** Tool results establish eligibility; current deterministic data supplies every returned card field.
- **Decision:** Preserve model nomination order and do no deterministic reranking. **Reason:** Choosing among validated candidates is an allowed model responsibility, while the contract exposes an ordered array. **Consequence:** The application filters but does not substitute products or reorder accepted choices.
- **Decision:** Reject invalid nominations individually and return the valid subset with HTTP 200. **Reason:** A schema-valid final answer remains useful even if one untrusted nomination fails business validation, and the contract has a dedicated recommendation-validation object. **Consequence:** Unknown/duplicate/ungrounded IDs never become cards and remain inspectable in trace validation errors.
- **Decision:** Compute product availability as all-positive=`in_stock`, all-zero=`out_of_stock`, mixed=`partial`. **Reason:** This uses every authoritative variant and gives distinct meaning to the contract's product-level states. **Consequence:** `JKT-003`, `JKT-002`, and `JKT-001` provide deterministic fixtures for the three reachable states.
- **Decision:** Leave `matched_variant` null in Phase 5. **Reason:** The requested nomination authority is product IDs only, and resolved shopper constraints/variant selection are not yet application-owned. **Consequence:** Phase 5 does not guess a variant from prose or tool-call order; later work must define an explicit variant nomination/constraint contract before populating it.
- **Decision:** Use `recommendation_validation.validation_errors` for rejected nominations and reserve trace `errors` for orchestration/tool-processing failures. **Reason:** The contract already separates recommendation validation from execution errors. **Consequence:** Evaluation can distinguish a safely filtered model choice from an infrastructure failure.
- **Decision:** Sanitize and cap every rejected nomination ID displayed in a validation error to 64 Unicode code points in application code. **Reason:** Model-generated identifiers are untrusted and must not inflate or split trace records, while this trace concern does not need extra OpenAI schema complexity. **Consequence:** Duplicate, unknown, and ungrounded errors remain useful and bounded without persisting the full rejected value.
- **Decision:** Keep price as Decimal internally and rely on the existing API serializer only at JSON output. **Reason:** Commerce-critical money must remain decimal-safe. **Consequence:** No new pricing calculation or floating-point authority enters Phase 5.

## Risks and follow-ups

- **Unsupported prose claims:** The structured cards are authoritative, but the model's free-form `message` may still phrase an unsupported fact. Keep grounding instructions strong and evaluate prose separately; do not parse prose into commerce fields.
- **Grounding extraction drift:** Tool result shapes may evolve. Use existing typed tool models and fail closed as `invalid_tool_evidence` if successful evidence cannot be validated; never mislabel that internal failure as malformed provider output.
- **Catalogue changes between tool use and hydration:** Re-fetching is intentional. A product removed after tool execution is rejected and recorded rather than returning stale data.
- **Availability interpretation:** The contract does not define aggregation. This plan's explicit all/some/none rule must be documented in README and tests; changing it later is a behavior change.
- **Matched variants:** Returning null means a card can be product-authoritative without identifying the shopper's exact requested size/colour. Populating this field should follow Phase 6 resolved constraints or another explicit contract, not an inference from prose.
- **Partial acceptance/message mismatch:** If a nomination is filtered, model prose may still mention it. The card remains safe and the trace exposes the rejection, but a future evaluator-driven phase may require deterministic message repair or a bounded model correction loop.
- **Structured-output refusal/incompletion:** A refusal or incomplete response that does not provide the strict final object continues through the existing safe malformed/failure path. A public refusal response contract is outside this phase.
- **Trace schema expressiveness:** There is no dedicated `all_products_grounded` or `duplicates_removed` boolean. Stable `validation_errors` carry that evidence without changing the contract.
- **Trace inflation or control-character injection:** A model may nominate an extremely long or multiline ID. Sanitize every rejected ID at the application trace boundary and cap its displayed form to 64 Unicode code points; test every rejection category.
- **Cross-turn recommendations:** Current-turn-only grounding means a shopper cannot rely on prior-turn candidates without the model searching/getting them again. Phase 6 should revisit grounding when backend conversation state becomes authoritative.
- **OpenAI schema/SDK drift:** Recheck official docs and the installed SDK before implementation and keep adapter tests exact. Because offline doubles cannot prove provider schema acceptance, run and record the manual live Phase 5 smoke before merge whenever developer credentials are available; never move it into pytest or CI.
- **Missing product specification:** If `docs/product-spec.md` is restored and contradicts availability, variant, or validation semantics here, update this ExecPlan before implementation and follow the authoritative specification.

## Outcome

Planning completed on 2026-08-29. No Phase 5 source, test, dependency, contract, fixture, configuration, or runtime behavior change has been implemented yet.

When implementation is complete, replace this paragraph with the shipped behavior, milestone results, exact validation commands and outcomes, deviations from the original design with reasons, and remaining limitations.
