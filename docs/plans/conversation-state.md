# Backend-Owned Conversation State

## Goal

Phase 6 gives the Sales Agent deterministic, backend-owned memory across shopper
turns that share the existing `session_id`. A shopper can establish constraints,
add another preference later, replace an earlier preference, or explicitly clear
one without restating the rest of the request. The application retains the
resulting normalized state and records exactly what changed on each successful
turn.

For example, these turns:

```text
Turn 1: I need a waterproof hiking jacket under £160.
Turn 2: I'd prefer blue.
Turn 3: Actually my budget is £120.
```

produce application-owned state equivalent to:

```text
activity = hiking
weather = [waterproof]
maximum_price = Decimal("120")
colour = blue
```

The second turn retains activity, weather, and budget while adding colour. The
third turn replaces only the budget and emits one trace change from 160 to 120.
The model identifies explicit shopper-intent updates in a strict final output;
deterministic application code validates, normalizes, merges, compares, and
commits them.

Every new shopper HTTP request starts a new OpenAI Responses chain assembled
from bounded backend context. `previous_response_id` remains limited to tool-call
continuations inside that one request. A product can become a new structured
recommendation card only when a successful commerce tool in the current shopper
turn establishes authoritative evidence for it, preserving Phase 5's grounding
boundary.

The feature is complete when realistic multi-turn retention, replacement,
clearing, isolation, rollback, ordering, context replay, recommendation
grounding, and trace behavior pass entirely offline; the public API contract is
unchanged; and the optional live smoke can verify the exact Phase 6 structured
output/context shape without becoming a pytest or CI dependency.

## Context and authoritative sources

Repository sources, in precedence order for this work:

- `AGENTS.md` requires backend-owned session state, deterministic commerce
  authority, Decimal-safe money, structured recommendations separate from prose,
  traceable constraint changes, offline tests, and no V1 database.
- `.agent/PLANS.md` defines this ExecPlan's required structure and living-document
  rules.
- `contracts/salesagent_api_contract.yaml` defines the unchanged chat and trace
  endpoints. Its `ResolvedConstraints` fields are exactly `category`, `activity`,
  `weather`, `features`, `maximum_price`, `colour`, `size`, `season`, and
  `priority`. Its `ConstraintChange` requires `field`, `previous`, and `current`.
- `data/products.json` and `data/discounts.json` remain authoritative for
  commerce facts. Shopper constraints describe intent; they do not update or
  override these files.
- `docs/plans/openai-agent-orchestration.md` records the completed Phase 4 loop,
  including its response/call bounds, safe failures, usage/tracing semantics,
  and deliberate use of `previous_response_id` only within one shopper turn.
- Phase 5 is represented in the inspected repository by local branch
  `feat/recommendation-hydration`, commits `90f245e` and `4e7aa25`. Its
  `docs/plans/recommendation-hydration.md` and implementation establish the
  strict `AgentFinalOutput`, current-turn grounded product IDs,
  `RecommendationHydrator`, authoritative card assembly, and accepted-ID trace
  semantics that Phase 6 must preserve.
- In that Phase 5 implementation, `src/salesagent/agent/final_output.py` defines
  final prose plus up to three nominated IDs; `agent/orchestrator.py` owns one
  Responses/tool loop and current-turn evidence; `agent/responses_client.py`
  isolates SDK request/response shapes; `services/recommendations.py` validates
  and re-fetches nominations; and `services/chat.py` builds the response and
  trace.
- `src/salesagent/api/models.py` already uses `Decimal` for
  `ResolvedConstraints.maximum_price` through `ApiMoney`, while `weather` and
  `features` are arrays and the other constraint values are nullable strings.
- `src/salesagent/repositories/traces.py` stores completed traces independently
  under a single lock. It is not a session-state repository and must not be used
  to reconstruct conversation state.
- `src/salesagent/main.py` is the application composition root. It creates
  process-local repositories and shares one `CommerceService` between the tool
  dispatcher and, after Phase 5, recommendation hydration.
- The complete tests under `tests/`, including the Phase 5 versions inspected
  from `feat/recommendation-hydration`, define the existing session-ID,
  turn-index, trace gating, orchestration, strict-output, recommendation, and
  safety behavior that Phase 6 must retain.

Two required planning inputs are not present on the active checkout:

- `docs/product-spec.md` is named as authoritative by `AGENTS.md` but is absent
  from both the active branch and the inspected Phase 5 tree. No unavailable
  product-spec behavior is assumed. If the file appears before implementation,
  read it first and reconcile any conflict in this plan's Discoveries and
  Decision log before changing source code.
- The active `feat/conversation-state` branch currently points to Phase 4 commit
  `e7671d7`. Consequently `docs/plans/recommendation-hydration.md`,
  `src/salesagent/agent/final_output.py`, `src/salesagent/services/recommendations.py`,
  and their tests are not in the working tree even though the Phase 6 brief calls
  them current Phase 5 inputs. Phase 6 implementation must first integrate or
  rebase onto `feat/recommendation-hydration` commit `4e7aa25`; it must not
  recreate or bypass Phase 5 from the older working tree.

Current official OpenAI documentation also constrains the design:

- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
  requires a root object, requires all fields in strict schemas, supports
  nullable fields to emulate optional values, permits valid nested `anyOf`
  schemas, and requires `additionalProperties: false` for strict objects.
- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
  documents manually supplied alternating user/assistant input messages for the
  Responses API as well as provider-managed continuation by
  `previous_response_id`.
- [Create a model response](https://developers.openai.com/api/reference/python/resources/responses/methods/create)
  accepts message-list `input`, strict `text.format`, and
  `previous_response_id`. The installed OpenAI Python 3.3.1 types permit
  `user`, `assistant`, `system`, and `developer` roles for easy input messages.
  The API role hierarchy gives `developer` and `system` messages precedence over
  `user` messages. Phase 6 therefore must not elevate shopper-derived constraint
  values merely because the application serialized them; the static
  `instructions` string remains the only developer-role content.

The project direction intentionally chooses bounded semantic replay rather than
persisting complete provider output items or reasoning. That is a product and
privacy boundary, not an attempt to reproduce an OpenAI chain across shopper
turns.

## Scope

This work includes:

- immutable application models for resolved constraints, recent successful
  conversation turns, and one session snapshot;
- an in-memory session repository keyed by the existing `session_id`;
- per-session synchronization and independent cross-session execution;
- a strict, field-specific constraint patch added to Phase 5's
  `AgentFinalOutput`;
- deterministic retain, set/replace, clear, normalization, equality, merge, and
  change-generation behavior;
- a bounded history of the six most recent successful user/assistant turns,
  including only canonical IDs for recommendations actually returned as cards;
- construction of each new Responses chain from an application context message,
  bounded role-correct history, and the current shopper message;
- preservation of Phase 4 within-turn function-call continuations and Phase 5
  current-turn recommendation grounding;
- transactional coordination in `ChatService` so failed turns do not mutate
  resolved constraints or history;
- full successful-turn trace population and unchanged-state failure traces;
- offline unit, repository, orchestrator, service, concurrency, API, contract,
  and safety tests;
- README updates and an optional, manually invoked live multi-turn smoke check;
- maintenance of this ExecPlan as implementation progresses.

Likely files created or changed after the Phase 5 baseline is integrated are:

```text
README.md
src/salesagent/domain/conversation.py                 # new immutable state values
src/salesagent/repositories/sessions.py               # new in-memory state/locks
src/salesagent/services/constraints.py                # new deterministic merger
src/salesagent/agent/final_output.py
src/salesagent/agent/instructions.py
src/salesagent/agent/responses_client.py
src/salesagent/agent/orchestrator.py
src/salesagent/services/chat.py
src/salesagent/main.py
scripts/smoke_openai_agent.py
tests/fakes.py
tests/test_constraint_state.py                        # new
tests/test_session_repository.py                      # new
tests/test_final_output.py
tests/test_instructions.py
tests/test_responses_client.py
tests/test_agent_orchestrator.py
tests/test_chat_service.py
tests/test_api.py
tests/test_smoke_openai_agent.py
docs/plans/conversation-state.md                      # kept current while executing
```

`src/salesagent/api/models.py` should remain behaviorally unchanged because it
already represents the contract. A narrow mapping helper may be added there only
if generated OpenAPI comparison proves necessary; the YAML contract must not be
changed for this phase. `repositories/traces.py`, commerce services, tool models,
tool definitions, and the dispatcher should not need behavior changes.

## Non-goals

Phase 6 does not add:

- database, Redis, file, browser, cookie, or distributed session persistence;
- authentication, accounts, cross-device identity, or ownership checks for a
  supplied session ID;
- frontend changes;
- OpenAI conversation objects or persisted response IDs across shopper turns;
- raw SDK response, reasoning, function-call internals, prompt, credential, or
  header storage in session state;
- unbounded transcript or arbitrary long-term memory;
- regex or keyword extraction from shopper prose;
- model authority over merge semantics or stored state mutation;
- new public constraint fields or an API contract change;
- a change to the four read-only commerce tools;
- historical grounding as permission to emit a recommendation card;
- inferred product attributes, prices, URLs, stock, promotions, or discounts as
  shopper constraints;
- promotion application, final-price calculation, basket/order mutation,
  autonomous purchase, RAG, embeddings, vector search, a production database,
  another model provider, or the external evaluation harness;
- guaranteed process-wide session retention under restarts or multi-worker
  deployment.

## Current state

The active branch is a Phase 4 checkout. `ChatService` preserves or generates a
session ID and increments a `_turn_indices` dictionary under one lock before it
calls the orchestrator. This means failed turns consume an index and receive a
failure trace. The service does not retain constraints or conversation text;
every call to `AgentOrchestrator.run` receives only the current `message`.

`AgentOrchestrator` starts every shopper request with
`previous_response_id=None`, applies the same developer instructions and tool
definitions on every provider call, and uses the preceding response ID only to
send correlated function outputs later in that same run. It enforces six
Responses calls, eight function calls, two identical call signatures, valid
unique call IDs, schema-validated dispatch, and safe provider failures.

`ResponseRequest.input` is currently either one string or a tuple of
`FunctionCallOutput` values. `OpenAIResponsesClient` maps the string directly or
maps the function outputs to SDK input items. It does not yet have an
application-owned message item for backend transcript replay.

Phase 5, on its local feature branch, changes the final no-tool output to a
strict JSON object with `message` and `nominated_product_ids`, supplies that
schema through Responses `text.format`, and derives `grounded_product_ids` only
from typed successful commerce evidence in the current `run` call. Its
`RecommendationHydrator` re-fetches each first-seen nomination, rejects unknown,
duplicate, and current-turn-ungrounded IDs, and returns authoritative cards.
`ChatService` writes accepted canonical IDs to
`trace.recommended_product_ids`. This is the required implementation baseline
for Phase 6.

The public `ResolvedConstraints` model already has the exact contract fields,
but every successful and failed trace currently receives a fresh empty value.
`constraint_changes` is always empty. `InMemoryTraceRepository` is keyed by
trace ID only and contains no session lookup or transaction API.

The current application creates one `ChatService` and one trace repository per
`create_app` call. This provides natural process-local isolation for a new
session repository. Evaluation traces are conditionally routable via
`SALESAGENT_ENABLE_EVAL_TRACES`; Phase 6 must not alter that gate.

## Proposed design

### Component boundaries

Use this concrete dependency direction after Phase 5 is present:

```text
FastAPI chat route
    -> ChatService (turn transaction, response, and trace coordinator)
        -> InMemorySessionRepository (state, turn counter, per-session lock)
        -> AgentOrchestrator (one current Responses/tool chain)
            -> ResponsesClient
            -> ToolDispatcher -> CommerceService
        -> ConstraintStateMerger (normalize, merge, semantic change evidence)
        -> RecommendationHydrator -> same CommerceService
        -> InMemoryTraceRepository
```

Keep constraint rules out of `ChatService`, prompt text, routes, and repository
locking code. Keep SDK input serialization out of state models. The repository
owns process-local storage and synchronization but not merge semantics. The
trace remains an observation of a turn, never the source from which current
state is rebuilt.

### Session-state data model

Add immutable internal models in `src/salesagent/domain/conversation.py`:

```text
ResolvedConstraintState
    category: str | None
    activity: str | None
    weather: tuple[str, ...]
    features: tuple[str, ...]
    maximum_price: Decimal | None
    colour: str | None
    size: str | None
    season: str | None
    priority: str | None

ConversationTurn
    user_message: str
    assistant_message: str
    recommended_product_ids: tuple[str, ...]

SessionState
    resolved_constraints: ResolvedConstraintState
    history: tuple[ConversationTurn, ...]
```

The repository separately owns the last reserved turn index for each session.
Do not use mutable `api.models.ResolvedConstraints` as the stored domain value,
and do not put trace IDs, provider response IDs, tool results, raw nominations,
or commerce facts in `SessionState`.

The state shape is fixed and all stored values have finite upstream bounds: a
user message is already capped at 4,000 characters by `ChatRequest`, assistant
text is bounded by the existing provider output-token setting, each successful
turn has at most three accepted recommendation IDs, and history has a fixed turn
count. Do not introduce a new dependency or generalized persistence interface
for a hypothetical database.

Map `ResolvedConstraintState` to the existing API `ResolvedConstraints` at the
service boundary. Keep `maximum_price` as `Decimal` until the existing
`ApiMoney` JSON serializer produces the contract's numeric representation.

### Strict constraint patch

Extend Phase 5's `AgentFinalOutput` by one required property named
`constraint_updates`. That property is a fixed object with exactly the nine
contract field names. Each property is required by the strict schema and is
either `null` or a field-appropriate update object:

```text
constraint_updates.category:       TextUpdate | null
constraint_updates.activity:       TextUpdate | null
constraint_updates.weather:        TextListUpdate | null
constraint_updates.features:       TextListUpdate | null
constraint_updates.maximum_price:  MoneyTextUpdate | null
constraint_updates.colour:         TextUpdate | null
constraint_updates.size:           TextUpdate | null
constraint_updates.season:         TextUpdate | null
constraint_updates.priority:       TextUpdate | null

TextUpdate
    operation: "set" | "clear"
    value: string | null

TextListUpdate
    operation: "set" | "clear"
    value: array[string] | null

MoneyTextUpdate
    operation: "set" | "clear"
    value: string | null
```

Semantics are deliberately explicit:

- A `null` field entry means retain the stored value and cannot produce a
  `ConstraintChange`.
- `{"operation":"set","value":...}` adds a previously absent constraint or
  replaces the complete prior value for that field.
- `{"operation":"clear","value":null}` removes a scalar/budget constraint or
  resets a list constraint to `[]`.
- `set` with `null`, `clear` with a non-null value, a blank scalar, a blank list
  item, an empty set-list, an invalid/negative/non-finite decimal, an extra
  field, or a wrong value type is rejected. No partial patch is merged.

For `weather` and `features`, `set` replaces that whole field. If the shopper
says “also breathable,” the model must use the supplied current state and emit
the complete intended value for `features`; application code does not infer an
append from prose. This keeps one deterministic set/replace rule for every
field. `clear` remains the only representation for removing the full list.

The model-facing budget is a decimal string such as `"120.00"`, not a binary
float and not a Pydantic-generated `Decimal` union. Application validation
constructs `Decimal` directly from the string. This follows the existing tool
schema workaround and avoids the provider incompatibility Phase 4 discovered
for generated Decimal schemas.

All objects must forbid additional properties and list every declared property
as required. The root remains `AgentFinalOutput`, an object rather than a root
union. Nested nullable objects are compatible with the documented strict-schema
subset. Pydantic model validators enforce operation/value combinations that
cannot be expressed with unsupported JSON Schema `if`/`then` rules. Invalid
final JSON or invalid patch semantics follows the existing safe
`malformed_model_response` path before `ChatService` receives a result.

Generate a fresh Phase 6 text format from the application model, and test its
complete shape. Do not hand-maintain a second divergent patch schema in the
prompt.

### Model and deterministic responsibilities

The model may:

- interpret which explicit preferences in the current shopper message are new,
  replaced, or cleared;
- emit only those field patches;
- use supplied state/history to understand references such as “make that £120”;
- choose among the four read-only tools and nominate current-turn-grounded IDs;
- write the shopper-facing response.

Deterministic code must:

- reject malformed patches and unknown fields;
- define retain/set/clear behavior;
- parse money with `Decimal`;
- normalize values and decide semantic equality;
- generate per-field change evidence from old and new application state;
- serialize full state to the trace;
- validate/hydrate recommendation IDs through the Phase 5 boundary;
- control locking and commit/rollback.

The model must not derive constraint updates from tool data, catalogue facts,
prior assistant claims, or product attributes unless the current shopper
message explicitly expresses that intent. This semantic identification is an
allowed model responsibility, but it never authorizes a commerce mutation.
Prompt wording guides it; strict field shape and deterministic merge are the
enforcement boundary for what can be stored.

### Normalization, equality, and change generation

Implement one `ConstraintStateMerger` in
`src/salesagent/services/constraints.py`. It accepts an immutable old state and
a validated patch and returns an immutable proposed state plus ordered internal
change evidence. It never mutates its input.

Normalize scalar text by trimming leading/trailing whitespace and collapsing
every internal whitespace run to one ASCII space. Preserve the normalized
display casing for a genuinely new value. Compare scalar values with
`casefold()` after whitespace normalization. If the new value is equal by this
rule, retain the exact already-stored display value and emit no change; casing
or whitespace alone must not churn state.

Normalize `weather` and `features` item-by-item with the same text rule, remove
case-insensitive duplicates, and sort by each item's `casefold()` key for stable
storage. Treat the lists as sets for equality. Reordering, duplicate entries,
case differences, and whitespace differences alone emit no change and preserve
the prior stored tuple. A real membership change replaces the stored normalized
tuple and emits one field-level change whose previous/current values are the
complete arrays.

Parse `maximum_price` directly with `Decimal`. Require a finite, nonnegative
value; do not round or quantize shopper input silently. Decimal equality makes
`120`, `120.0`, and `120.00` the same budget, so an equivalent spelling emits no
change and retains the prior Decimal representation. The domain and API mapping
perform no binary floating-point calculation.

Clear maps scalar and budget fields to `None`, and list fields to an empty tuple.
Clearing an already-empty value is a semantic no-op and emits no change. Setting
a normalized value equal to the stored value is also a no-op. The merger emits
real changes in the fixed contract field order listed above, independent of
model serialization details.

Keep internal `ConstraintStateChange` evidence separate from the HTTP model so
domain/service code does not depend on API classes. In `ChatService`, project
the old and new states through `ResolvedConstraints.model_dump(mode="json")`
and create public `ConstraintChange` values from those projections. This makes
`previous` and `current` use the same null, array, string, and numeric money
representations as `resolved_constraints` without using float arithmetic for
state or comparison.

### Bounded conversation history

Retain exactly the six most recent successful `ConversationTurn` values per
session. Six turns cover the specified three-turn flow plus several consultative
follow-ups while keeping replay, token use, and process memory bounded. On a
seventh success, drop the oldest complete turn; never split a user/assistant
pair. A failed turn is traceable but is not appended to history.

For each successful turn, store only:

- the already validated `ChatRequest.message` exactly as received;
- the final shopper-facing `AgentFinalOutput.message` exactly as returned;
- the canonical product IDs of cards actually emitted after Phase 5 hydration,
  in response order.

Do not retain final-output JSON, rejected/raw nominations, product facts, tool
arguments/results, traces, token usage, errors, hidden instructions, reasoning,
raw SDK items, response IDs, API credentials, headers, or promotion data in the
history.

The next initial Responses input is constructed in this exact order:

1. For each stored turn from oldest to newest, one `user` message with the prior
   shopper text followed by one `assistant` message. The assistant content is a
   compact JSON object containing `message` and the authoritative
   `recommended_product_ids` actually returned on that turn. This preserves role
   semantics, natural prose, and product-reference IDs without replaying tool
   internals.
2. One application-generated `user` message containing a compact JSON envelope
   with a fixed discriminator such as `"type":"salesagent_context"` and the
   complete normalized `resolved_constraints`. Serialize `maximum_price` as a
   canonical decimal string in this internal context to avoid float conversion.
   This message is bounded application context/data at the same lower-trust role
   as the shopper material from which its values originated. It is not a new
   constraint update, a commerce fact, or an instruction. Placing it after old
   history makes the current snapshot unambiguous without elevating it above the
   shopper role.
3. One final `user` message containing only the current shopper request.

The static `DEVELOPER_INSTRUCTIONS` supplied through the Responses
`instructions` parameter describe how to interpret the distinguished context
envelope and remain the only developer-role input. They tell the model that the
snapshot is the application's resolved state before the current message, that
old history must not override it, and that only explicit intent in the final
current shopper message may produce constraint updates. The model can use the
snapshot to resolve “that” or “actually” references, but backend merge semantics
remain authoritative even if the model disregards this guidance.

The context builder escapes all content through normal JSON serialization and
never interpolates values into executable code or tool definitions. Constraint
values still originate in shopper intent and are not commerce facts. A value
that resembles an instruction remains JSON data inside a `user` message and is
never copied into `instructions` or any developer/system message. The four
read-only tools, argument validation, deterministic merge, and recommendation
hydration remain the security boundary even if a shopper tries to store
prompt-like text as a preference.

### Responses request construction

Add an application-owned `ResponseMessage` value to
`agent/responses_client.py` with `role` restricted to `user | assistant` and
`content`. Dynamic `developer` and `system` roles are deliberately
unrepresentable at this application boundary. Narrowly extend
`ResponseRequest.input` to accept either the existing single string, a tuple of
`ResponseMessage` values, or a tuple of existing `FunctionCallOutput` values.
`OpenAIResponsesClient` maps message values to easy input messages and leaves
function-output mapping unchanged. It must reject or make unrepresentable a
mixed tuple rather than guess how to serialize it.

Change `AgentOrchestrator.run` to accept the current user message plus an
immutable application context containing resolved constraints and bounded
history, or accept the already constructed tuple if that keeps the dependency
cleaner during implementation. The orchestrator's first `ResponseRequest` uses
the complete message tuple and `previous_response_id=None`.

After a model function call, continuation requests remain exactly as in Phase
4/5: input is only correlated `FunctionCallOutput` values and
`previous_response_id` is the immediately preceding response ID. Re-send static
instructions, tools, and the strict Phase 6 text format on every continuation.
The initial message-list context is already in that provider chain and should
not be duplicated in every function output request.

Never return a provider response ID from `run`, put one in a session model, or
retrieve one at the start of another shopper turn. A new HTTP turn always begins
with `previous_response_id=None`, even for an existing session. Keep the current
within-turn `store=True` behavior unless a separate provider-retention task
changes Phase 4's continuation design.

### Transaction and turn-index behavior

`ChatService.chat` coordinates one turn under the session's lock:

```text
resolve/generate session_id
acquire that session's lock
reserve next turn_index
read immutable constraints/history snapshot
build backend context
run one orchestrator chain
validate and merge its typed constraint patch into a proposed state
hydrate/validate current nominations using current-turn grounding
construct and validate ChatResponse and successful TraceResponse
store the successful trace
commit proposed constraints plus appended/truncated successful history
release session lock
return response
```

Do not mutate constraints or history before orchestration, merge, recommendation
hydration, and response/trace construction all succeed. Storing the already
validated trace immediately before the repository's simple in-memory state
assignment means an unexpected trace-storage failure also leaves conversation
state unchanged. The session commit itself is a single replacement of an
immutable state value while the lock is held.

If orchestration or final-output validation fails, build the existing safe
failure trace with the pre-turn snapshot as `resolved_constraints`, an empty
`constraint_changes`, no returned recommendations, and the actual safe
tool/error evidence available under Phase 5 rules. Store it, release the lock,
and raise the unchanged generic shopper-facing failure. Do not append the failed
user message or any partial assistant/tool content to history.

Preserve existing turn-index semantics: reserve and increment the operational
per-session counter before the provider call, and do not roll it back on failure.
A failure at index 2 is followed by the next attempt at index 3. Turn index is
attempt/trace metadata, not part of the transactional shopper constraint/history
state.

Unexpected non-orchestration exceptions must also release the session lock via
a context manager and must not commit conversation state. Preserve existing
safe exception boundaries; if implementation adds a safe internal category for
a newly reachable deterministic failure, record that narrow decision before
changing code or tests.

### In-memory concurrency

`InMemorySessionRepository` owns:

- a mapping from `session_id` to immutable `SessionState`;
- a mapping from `session_id` to a dedicated `threading.Lock`;
- a mapping from `session_id` to its last reserved turn index;
- one short-lived registry lock used only to create/find those per-session
  entries.

Expose a context-managed session transaction/lease so callers cannot forget to
release the lock. The registry lock must not be held during OpenAI calls,
commerce calls, hydration, trace construction, or trace storage. Once the
dedicated lock is obtained, one request owns that session from snapshot through
trace/store or failure. Requests for different session IDs use different locks
and can proceed concurrently in FastAPI's worker threads.

Two simultaneous requests with the same session ID are serialized in lock
acquisition order. The first holder observes the prior state and commits or
rolls back before the next holder snapshots it, preventing lost updates and
interleaved turn histories. Truly simultaneous network requests have no stronger
wall-clock ordering guarantee; the assigned `turn_index` is the authoritative
serialized order. No Redis, async/distributed lock, optimistic retry, or global
turn-duration lock is needed for V1.

Use one lock order everywhere: session lock before the trace repository's
internal lock. No code should acquire a session lock while holding the trace
lock. Add deterministic event/barrier-based tests rather than timing-dependent
sleep assertions.

### Recommendation grounding across turns

Retained constraints, prior user/assistant prose, and prior accepted product IDs
may help the model understand a follow-up. They do not enter
`OrchestrationResult.grounded_product_ids` and do not authorize a card.

Keep Phase 5's grounding set local to the current `AgentOrchestrator.run` call.
For every turn, derive it only from typed successful current-turn
`search_products`, `get_product`, and qualifying `check_inventory` results. A
historical card, model prose, user-supplied ID, stored recommendation ID, raw tool
argument, or catalogue existence alone cannot bypass this rule.

Therefore a shopper may ask “Does the first jacket come in blue?” and history
can tell the model which product ID was discussed, but a new structured card for
that product requires a current-turn `get_product`, `search_products`, or
qualifying inventory result. `RecommendationHydrator` still re-fetches accepted
IDs and supplies every card fact from current commerce data. Historical IDs are
reference context only.

### Trace semantics

For every successful turn:

- `resolved_constraints` is the complete normalized application-owned state
  after applying this turn's accepted patch, including retained values.
- `constraint_changes` contains only semantic changes made by this turn, in
  fixed contract-field order. Each item uses the exact field name and the old
  and new public representations; adding uses `null -> value`, replacing uses
  `old -> new`, and clearing uses `value -> null` or `array -> []`.
- Retain operations and normalization-equivalent set/clear no-ops do not emit a
  change.
- `recommended_product_ids` keeps Phase 5's meaning: canonical IDs of cards
  actually emitted in this turn, in card order. It is not a session-level list.

For a failed turn, trace the unchanged pre-turn `resolved_constraints` and
`constraint_changes=[]`. Preserve its reserved `turn_index`, current user
message, safe tool/error evidence, usage, and latency. Never expose session
history, hidden prompts, raw model patches, credentials, reasoning, or SDK
objects in the trace.

Do not reconstruct current state by querying or folding prior traces. Session
state and traces have independent repositories and purposes.

### Application assembly and restart behavior

Create one `InMemorySessionRepository` in `create_app` and inject it into
`ChatService` beside the trace repository, orchestrator, merger, and hydrator.
Keep it on `application.state` only if the existing safe developer diagnostics
or deterministic tests need direct access; do not add a public session endpoint.

Each `create_app` instance has isolated sessions. Restarting the process, making
a new app instance, or routing the same session ID to another worker starts with
empty constraints/history and turn index 1. Document that limitation in README.
Multi-worker affinity/distributed storage is a production follow-up, not V1
scope.

## Milestones

### Milestone 1 — Establish the Phase 5 baseline and state models

#### Outcome

The implementation branch includes Phase 5 and has immutable internal values
for exact contract-aligned constraints, bounded conversation turns, and session
state, without changing chat behavior yet.

#### Implementation

- Integrate/rebase onto `feat/recommendation-hydration` commit `4e7aa25` before
  source edits. Resolve conflicts by preserving Phase 5 behavior and this plan;
  do not copy files manually from the Phase 4 branch.
- If `docs/product-spec.md` has appeared, read and reconcile it before
  proceeding.
- Add `domain/conversation.py` with the three immutable state values described
  above and `MAX_HISTORY_TURNS = 6` near the history invariant.
- Require all nine and only nine resolved constraint concepts internally, using
  `Decimal` for budget and tuples for list fields.
- Add focused model tests for defaults, immutability, exact fields, Decimal
  retention, and six-turn truncation helper behavior.

#### Validation

- `uv run pytest tests/test_final_output.py tests/test_recommendations.py`
- `uv run pytest tests/test_constraint_state.py -k "model or history"`
- Phase 5 strict output and recommendation tests remain green before Phase 6
  output changes are introduced.

### Milestone 2 — Add the strict constraint-update contract

#### Outcome

One valid Phase 6 final model object carries shopper prose, nominations, and an
unambiguous patch in which every field is retain, set/replace, or clear.

#### Implementation

- Add strict text/list/money update models and the fixed nine-field patch to
  `agent/final_output.py`.
- Add `constraint_updates` to `AgentFinalOutput` and its generated Responses
  `text.format`.
- Use decimal strings at the model boundary and validate operation/value
  invariants without float conversion.
- Ensure every strict object has all properties required and
  `additionalProperties: false`, while the root remains an object.
- Update fake final-output builders so every scripted final supplies an explicit
  retain-all patch by default and can override selected fields succinctly.

#### Validation

- `uv run pytest tests/test_final_output.py`
- Tests cover retain-all, one/many sets, clears, exact nine fields, Decimal text,
  extras, blanks, empty lists, negative/non-finite budgets, invalid
  operation/value combinations, and schema freshness.
- A schema-walk assertion proves all object properties are required, strict
  objects forbid extras, and no root-level `anyOf` is generated.

### Milestone 3 — Implement deterministic normalization and merging

#### Outcome

A typed patch deterministically produces the proposed full state and exact
semantic per-turn changes without OpenAI, HTTP, or repository participation.

#### Implementation

- Add `services/constraints.py` with `ConstraintStateMerger`, immutable merge
  result/change evidence, and one shared text normalization helper.
- Implement fixed-order retain/set/clear logic, Decimal parsing/equality,
  casefolded scalar equality, set-like list equality, duplicate removal, and
  stable list ordering.
- Preserve the old stored display form on normalization-equivalent no-ops.
- Make merge all-or-nothing and independent from API models.

#### Validation

- `uv run pytest tests/test_constraint_state.py -k "merge or normalize or change"`
- Tests cover null-to-value additions, 160-to-120 replacement, colour clearing,
  retained fields, clearing empty fields, equal Decimal spellings, scalar
  casing/whitespace, list order/case/duplicates, real list replacement, fixed
  change order, and no mutation of the input state.

### Milestone 4 — Add the in-memory session repository and locking

#### Outcome

Session snapshots, successful commits, history truncation, and turn reservations
are isolated by session and safe under simultaneous synchronous requests.

#### Implementation

- Add `repositories/sessions.py` with per-session state/counter/lock maps and a
  short-held registry lock.
- Expose a context-managed lease that reserves the next turn index, returns an
  immutable snapshot, and permits at most one successful immutable-state commit.
- Keep failed-turn index reservations while leaving constraints/history
  unchanged.
- Append/truncate history only as part of a successful commit.
- Avoid a global lock around provider or commerce work.

#### Validation

- `uv run pytest tests/test_session_repository.py`
- Tests prove independent defaults, state isolation, incrementing indices,
  failure-index retention, six-turn truncation, immutable snapshots, and invalid
  double/out-of-lease commits.
- Event-controlled thread tests prove a second request for one session cannot
  snapshot before the first releases, while another session can enter before
  the first is released. No test relies only on elapsed time.

### Milestone 5 — Pass bounded backend context into Responses

#### Outcome

Every new shopper turn starts a fresh Responses chain containing normalized
backend state, exactly the retained role-correct transcript, accepted historical
IDs, and the current message; within-turn continuation behavior is unchanged.

#### Implementation

- Add `ResponseMessage` and the narrow message-list input variant to
  `responses_client.py`; restrict it to `user | assistant` and map it to official
  SDK input dictionaries. Do not add dynamic developer/system message support.
- Add a deterministic context serializer/builder at the orchestrator boundary.
- Change `AgentOrchestrator.run` to receive the context snapshot and construct
  the exact initial input sequence.
- Keep continuation inputs as `FunctionCallOutput` values and keep every new
  run's initial `previous_response_id=None`.
- Bump `PROMPT_VERSION` to `phase6-v1` and explain explicit current-message
  updates, full-field list replacement, retain/set/clear, application context,
  and the prohibition on commerce-derived constraints.
- Retain Phase 4 response/call/repetition bounds and Phase 5 grounding evidence.
- Keep `DEVELOPER_INSTRUCTIONS` as the only developer-role content. Send old
  user/assistant pairs first, then the distinguished user-role state envelope,
  then the current shopper message as the final user message.

#### Validation

- `uv run pytest tests/test_responses_client.py tests/test_agent_orchestrator.py tests/test_instructions.py`
- Adapter tests assert exact message roles/content, prove no input item has a
  developer/system role, and reject mixed input tuples.
- Orchestrator tests assert the first request has backend context/history/current
  input in the specified order and no previous ID, while later function-output
  requests use only the immediately preceding ID and reapply the same static
  instructions/tools/text format.
- A shopper-derived constraint value that looks like an instruction remains
  escaped inside the user-role context envelope and never appears in
  `ResponseRequest.instructions` or a privileged message role.
- Tests assert history product IDs do not appear in current-turn grounded IDs.

### Milestone 6 — Integrate transactional state into ChatService

#### Outcome

Successful turns atomically update constraints/history and expose the new state;
terminal failures preserve prior conversation state while retaining current
turn-index and safe trace behavior.

#### Implementation

- Inject the session repository and merger into Phase 5 `ChatService` from
  `create_app`.
- Hold one session lease from snapshot through trace/store/commit.
- Merge the final patch, hydrate recommendations, construct validated response
  and trace objects, store the trace, then commit proposed state and one bounded
  successful history turn.
- Map internal state/change evidence to existing API models.
- On terminal orchestration failure, trace the unchanged snapshot with no
  changes, store no history, and preserve the generic HTTP 500.
- Keep current promotion/pricing null and preserve evaluation trace gating.

#### Validation

- `uv run pytest tests/test_chat_service.py tests/test_api.py -k "state or constraint or failed or turn"`
- Service tests prove commit-on-success, no commit on failure, failed index
  consumption, unchanged failure traces, accepted-card IDs in history, no raw
  nominations, and six-turn eviction.
- A multi-threaded service test proves two same-session patches are serialized
  without a lost update or corrupt history.

### Milestone 7 — Preserve cross-turn recommendation grounding

#### Outcome

Prior recommendations are understandable in follow-ups but cannot become new
cards without fresh current-turn commerce evidence.

#### Implementation

- Keep `grounded_product_ids` scoped to each orchestrator run.
- Pass prior accepted IDs only as bounded reference context.
- Do not change `RecommendationHydrator` eligibility or authoritative re-fetch
  behavior.
- Ensure the successful history stores only post-hydration accepted canonical
  IDs.

#### Validation

- `uv run pytest tests/test_agent_orchestrator.py tests/test_recommendations.py tests/test_chat_service.py -k "ground or history or follow"`
- Turn 1 can emit a grounded card. Turn 2 can discuss it from history, but a
  nomination without a current tool result is rejected as ungrounded. A Turn 2
  `get_product` or qualifying `check_inventory` call re-establishes evidence and
  permits the card.
- Tests prove old tool results, old assistant prose, and old accepted IDs never
  populate the current grounding set.

### Milestone 8 — Complete multi-turn API, trace, safety, and documentation coverage

#### Outcome

The required realistic conversations work through the unchanged HTTP API, every
trace has exact state/change semantics, and V1 persistence/security limits are
documented.

#### Implementation

- Add scripted offline API scenarios for retention, replacement, clearing,
  contradictory preferences, independent sessions, failed turns, and grounded
  product follow-ups.
- Add a history-bound scenario exceeding six successful turns and inspect the
  next recorded `ResponseRequest`.
- Compare generated FastAPI schemas with the unchanged YAML contract.
- Update README with backend ownership, six-turn history, restart/multi-worker
  limitations, current-turn grounding, and no raw provider state.
- Add injection-shaped preference tests that prove extra commerce/configuration
  fields cannot enter the patch/state and cannot bypass deterministic tools or
  hydration.

#### Validation

- `uv run pytest tests/test_api.py`
- The three-turn jacket example ends with the expected full state and only the
  appropriate changes per trace.
- The response contract is unchanged, trace state is normalized, failed traces
  show unchanged state, independent sessions do not leak, and trace-disabled
  applications still omit the evaluation route.

### Milestone 9 — Full regression and optional live multi-turn smoke

#### Outcome

All offline checks pass on the Phase 6 implementation, the plan reflects what
shipped, and provider acceptance of the exact strict patch/context schema is
verified manually when credentials are available.

#### Implementation

- Update `scripts/smoke_openai_agent.py` to perform a bounded two- or three-turn
  same-session scenario that sets, retains, and replaces constraints and obtains
  at least one currently grounded recommendation.
- Keep smoke output to safe summaries: prompt/model version, turn indices,
  constraint field names changed, accepted recommendation IDs/count, tool count,
  token total, latency, and safe failure category. Never print prompts, shopper
  or assistant prose, constraint values, raw context, SDK objects, reasoning,
  credentials, headers, or provider exception text.
- Run every command below, inspect the diff for scope, and update Progress,
  Discoveries, Decision log, Risks, and Outcome with actual evidence/deviations.

#### Validation

- Run the complete Validation commands section.
- If `OPENAI_API_KEY` is available, run the optional manual smoke and record the
  result. If unavailable, record it as not run; do not claim provider acceptance.
- Confirm pytest and CI never invoke the smoke or require network/API
  credentials.

## Test plan

### Unit tests

- Final-output models and generated schema cover all strict patch shapes and
  reject ambiguous set/clear values, extras, invalid money, and partial objects.
- `ConstraintStateMerger` covers exact retain/set/clear semantics, every public
  field, normalization, semantic equality, stable ordering, Decimal safety,
  fixed change order, and immutable input.
- Context construction emits alternating bounded role-correct history, one
  distinguished user-role normalized-state envelope, accepted recommendation
  IDs only, and the current shopper text as the final user message.
- Responses mapping preserves message roles and existing function-call-output
  mapping without exposing SDK objects.
- Every request's developer `instructions` remains exactly the static versioned
  constant; no shopper-derived value is concatenated into it.
- Session repository tests cover defaults, commit, rollback-by-omission,
  counters, history truncation, isolation, and deterministic per-session
  synchronization.

### Integration and API tests

- Retention: waterproof hiking under 160 followed by blue retains the first
  constraints and adds only colour.
- Replacement: 160 followed by “make that 120” changes budget exactly once and
  traces 160 to 120 using the contract representation.
- Clearing: blue followed by “I don't care about colour” produces colour null
  and one clear change.
- Contradiction: a later explicit activity/season/priority preference replaces
  only the relevant old field.
- List behavior: a real feature/weather update replaces the complete list;
  equivalent reordered/case-varied lists do not create false changes.
- Independent sessions never share state, history, locks, or counters.
- A terminal provider/orchestration failure consumes its turn index, traces the
  unchanged snapshot, does not append history, and does not apply its proposed
  patch.
- The next success after failure sees only the last committed state/history.
- A new application instance loses prior state and starts the reused ID at turn
  1, as documented.
- A prior recommendation is referenceable, but a current card requires a new
  qualifying tool result.
- Response cards and `recommended_product_ids` preserve all Phase 5 authority
  and order semantics.
- More than six successful turns replay only the newest six complete pairs.
- Generated OpenAPI remains compatible with
  `contracts/salesagent_api_contract.yaml`.

### Concurrency tests

- Use `threading.Event`, a blocking fake orchestrator, and explicit entry/order
  records to prove same-session serialization without sleeps.
- The second same-session call must not enter orchestration until the first has
  committed or failed and released its lease.
- Two updates from simultaneous same-session calls appear at consecutive turn
  indices with the later snapshot including the earlier committed state; no
  update or history pair is lost.
- A different-session call can enter and complete while the first session is
  deliberately blocked.
- A failed first call releases its lock; the waiting call proceeds with unchanged
  constraints/history and the next index.

### Failure and security paths

- Malformed final JSON or patch data follows safe
  `malformed_model_response` handling and cannot partially update state.
- Hydration/response/trace construction failures before commit leave state and
  history untouched.
- Prompt-like text in a preference remains bounded user-intent data and cannot
  create fields outside the exact constraint patch.
- Product descriptions or tool results cannot silently become shopper
  constraints.
- Historical IDs, raw nominations, user claims, and product existence do not
  bypass current-turn grounding.
- No state, trace, response, or smoke output contains hidden instructions,
  reasoning, API keys, authorization headers, raw SDK responses, or provider
  exceptions.
- The four read-only dispatcher tools and their schema-validation boundary remain
  unchanged.

### Test doubles

Continue using the application-owned `ScriptedResponsesClient` and
`ModelResponse` snapshots. Extend `final_output_json` to create valid Phase 6
patches; do not make the fake infer constraints, merge state, ground products,
or hydrate cards. Use the real `ConstraintStateMerger`, tool dispatcher,
commerce service, repositories, and product fixtures in service/API integration
tests. Use small blocking fakes only to control concurrency order. No default
test may make an external OpenAI request.

## Security and trust-boundary checks

- **Model output cannot override commerce data:** Constraint updates contain
  shopper intent only. No patch field can address product records, IDs, price,
  URL, stock, promotion, discount, tools, prompt version, or configuration.
- **Product IDs remain validated:** Phase 5 validates and re-fetches every
  nomination; old accepted IDs are context only and never current evidence.
- **Tools stay read-only and schema validated:** All four existing tools continue
  through `ToolDispatcher`; state code does not dispatch arbitrary names or
  duplicate commerce rules.
- **Money stays Decimal-safe:** Budget input is parsed from a decimal string into
  `Decimal`, compared/stored without float, and converted only by the existing
  public JSON serializer. No Phase 6 price calculation is introduced.
- **Stock/price/URL/discount authority is unchanged:** Constraint state cannot
  modify or synthesize these values, and recommendation hydration remains the
  card boundary.
- **Prompt injection cannot mutate hidden state:** Only the fixed strict patch is
  considered, application code controls merge, and unknown fields fail. Tool
  results or prose never become mutation commands.
- **Shopper-derived context is not privilege-elevated:** Resolved constraint
  values are JSON-escaped in a distinguished `user` message. Static versioned
  instructions are the only developer-role input, and `ResponseMessage` does not
  represent developer/system roles.
- **State and history are bounded:** The schema has fixed fields and a session
  retains six successful pairs only; output and request limits remain in force.
- **Session data is minimized:** Store the successful user/assistant transcript
  and accepted IDs only, not provider internals, reasoning, tools, prompts,
  traces, or secrets.
- **Trace output stays safe:** Traces expose normalized public state and semantic
  changes, not raw patches or session history. Existing safe tool/error mapping
  and route gating remain.
- **Cross-session isolation is tested:** A supplied ID addresses only its own
  process-local record. Authentication/ownership is explicitly outside V1 and
  must be addressed before treating IDs as secure customer sessions.
- **No evaluation hard-coding:** Production code contains no scenario phrases,
  golden prompts, or product-ID special cases.

## Validation commands

Run from the repository root after Phase 5 is integrated and each applicable
milestone is complete:

```bash
uv sync
uv run pytest tests/test_final_output.py tests/test_constraint_state.py tests/test_session_repository.py tests/test_responses_client.py tests/test_agent_orchestrator.py tests/test_recommendations.py tests/test_chat_service.py tests/test_api.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -c "from salesagent.main import app; print(app.title)"
git diff --check
```

Successful output means dependency synchronization introduces no unplanned
dependency; all tests run offline; the focused and full suites pass; lint,
formatting, and strict type checks pass; importing the app without an API key
still prints `Sales Agent`; generated API behavior remains contract-compatible;
and the diff has no whitespace errors.

When developer credentials are available, run the separate, potentially
billable smoke manually:

```bash
OPENAI_API_KEY=... uv run python scripts/smoke_openai_agent.py
```

It passes only if the configured provider accepts the exact Phase 6 strict
output schema and message-list input, completes the multi-turn same-session
scenario, preserves/replaces expected constraints, and emits any asserted card
only after current-turn commerce grounding. It must not be invoked by pytest or
CI. If credentials are unavailable, record that it was not run.

## Progress

- [x] 2026-09-05: Read `AGENTS.md`, `.agent/PLANS.md`, the API contract, the
  completed Phase 4 plan/implementation, all current tests, and the Phase 5 plan,
  implementation, and tests from local branch `feat/recommendation-hydration`.
- [x] 2026-09-05: Verified current official OpenAI Structured Outputs,
  manually managed Responses context, request input, and
  `previous_response_id` documentation; inspected the installed SDK's accepted
  easy-message roles.
- [x] 2026-09-05: Documented the missing product specification and Phase 5
  baseline branch conflict; created this Phase 6 implementation plan only.
- [x] 2026-09-05: Architecture review moved shopper-derived resolved-state
  context from a dynamic developer message to a distinguished user-role data
  envelope; updated design, milestone, tests, security checks, and decision
  rationale only, with no implementation work.
- [ ] Milestone 1 — Establish the Phase 5 baseline and state models.
- [ ] Milestone 2 — Add the strict constraint-update contract.
- [ ] Milestone 3 — Implement deterministic normalization and merging.
- [ ] Milestone 4 — Add the in-memory session repository and locking.
- [ ] Milestone 5 — Pass bounded backend context into Responses.
- [ ] Milestone 6 — Integrate transactional state into ChatService.
- [ ] Milestone 7 — Preserve cross-turn recommendation grounding.
- [ ] Milestone 8 — Complete multi-turn API, trace, safety, and documentation
  coverage.
- [ ] Milestone 9 — Full regression and optional live multi-turn smoke.

## Discoveries

- The active `feat/conversation-state` branch and `origin/main` stop at Phase 4,
  while complete Phase 5 work exists only on local
  `feat/recommendation-hydration`. This matters because the requested “smallest
  extension” to `AgentFinalOutput` and recommendation-grounding regression tests
  are impossible against the active tree until Phase 5 is integrated.
- `docs/product-spec.md` is absent from both inspected trees. This matters
  because the API contract and existing implementation are the only available
  sources for constraint types; any restored product specification must be
  reconciled before implementation.
- The current turn counter lives inside `ChatService`, is incremented before
  orchestration, and is not rolled back on failure. This matters because moving
  it into the session repository must preserve failed-turn index consumption
  even though conversational state is transactional.
- Phase 5's final-output boundary already has exactly the two fields Phase 6
  needs to preserve and sends one strict `text.format` on every within-turn
  request. This makes one new `constraint_updates` property the narrowest model
  output change.
- Phase 4 previously found provider rejection of Pydantic's generated Decimal
  union in a strict tool schema and uses a nullable decimal string at the model
  boundary. This matters because maximum-price updates should follow the same
  proven string-to-Decimal pattern.
- Official Structured Outputs rules require all strict fields but allow null to
  emulate optionality. This matters because fixed nullable patch fields can mean
  retain without an unsupported optional-property schema or a prose parser.
- Pydantic semantic validators are not fully represented by JSON Schema, and the
  documented strict subset does not support `if`/`then`. This matters because
  set/non-null and clear/null coupling must be validated again in application
  code even when Structured Outputs guarantees the outer shape.
- Official Responses examples accept manually supplied alternating user and
  assistant messages, and the current API/installed SDK define developer/system
  roles as higher-priority instructions. This matters because backend context
  can be replayed as a user-role data envelope without preserving response IDs,
  raw SDK output, or elevating shopper-derived values to developer authority.
- Phase 5's grounding set is created inside one `AgentOrchestrator.run` and
  `RecommendationHydrator` independently re-fetches accepted products. This
  matters because adding history does not require weakening or redesigning the
  recommendation authority boundary.
- `ConstraintChange.previous/current` are intentionally unconstrained in the
  YAML contract, while `ResolvedConstraints.maximum_price` has the public money
  serializer. This matters because change values should be projected through
  old/new public constraint models so budget traces use the same contract
  representation rather than raw model strings.
- FastAPI's synchronous route runs application work in worker threads. This
  matters because `threading.Lock` and per-session lock granularity fit the
  current architecture without introducing asyncio synchronization or external
  infrastructure.

## Decision log

- **Decision 1 — Session-state data model:** Store one immutable
  `ResolvedConstraintState` and up to six immutable `ConversationTurn` values per
  session, with the operational turn counter alongside them in the repository.
  **Reason:** This contains exactly the backend context needed for V1 and keeps
  domain state independent from HTTP/SDK models. **Consequence:** No provider ID,
  trace, tool payload, or commerce fact enters session state.
- **Decision 2 — History contents and bound:** Retain the last six successful
  complete user/assistant pairs plus accepted canonical card IDs. **Reason:** It
  is enough for short consultative follow-ups and provides a hard per-session
  replay bound. **Consequence:** Older conversational wording is forgotten while
  the full resolved constraint snapshot remains until cleared or restart.
- **Decision 3 — Patch representation:** Add one required fixed-field
  `constraint_updates` object whose nine required properties are nullable
  field-specific update objects. **Reason:** It is strict-output-compatible,
  type-specific, duplicate-proof, and is the smallest top-level extension to
  Phase 5. **Consequence:** Every model final emits explicit null retains for all
  unchanged fields.
- **Decision 4 — Retain/set/clear semantics:** Null means retain; `set` adds or
  replaces the complete field; `clear` with null resets it; semantic no-ops
  produce no change. **Reason:** Application-owned merge behavior must not depend
  on prose, omitted full state, or model interpretation after parsing.
  **Consequence:** List additions require the model to emit the complete intended
  value for that changed list field.
- **Decision 5 — Normalization and equality:** Collapse whitespace and compare
  scalar text case-insensitively; normalize/deduplicate/sort list fields and
  compare them as sets; compare finite nonnegative budgets as Decimal values.
  Preserve the old display value for equivalent updates. **Reason:** Superficial
  formatting must not create false changes. **Consequence:** Traces contain only
  semantic shopper-intent changes in stable field order.
- **Decision 6 — Commit/rollback:** Build the proposed state, hydration,
  response, and trace without mutation; store the validated trace and then
  replace the immutable session state once. **Reason:** Terminal model,
  validation, hydration, response, or trace-storage failure must not partially
  mutate conversation state. **Consequence:** Failed user/assistant content and
  patches are absent from later context.
- **Decision 7 — Same-session concurrency:** Hold a dedicated synchronous lock
  for the complete turn from snapshot through commit/failure trace. **Reason:**
  This is the simplest serializable in-memory design and prevents lost updates.
  **Consequence:** Long provider calls queue only requests for the same session.
- **Decision 8 — Cross-session isolation:** Use a short registry lock only to
  create/find per-session entries, then operate under different locks.
  **Reason:** Unrelated shoppers must not wait behind another session's model
  call. **Consequence:** Different sessions can run concurrently and have wholly
  separate constraints, histories, and counters.
- **Decision 9 — Backend context transport:** Start each run with six or fewer
  alternating historical user/assistant pairs, then one distinguished
  application-generated `user` message containing the resolved-state JSON
  envelope, then the current shopper text as the final `user` message. Assistant
  history is JSON containing prose and accepted IDs only. Static
  `DEVELOPER_INSTRUCTIONS` remains the sole developer-role content, and
  `ResponseMessage` represents only user/assistant roles. **Reason:** Constraint
  values ultimately originate with the shopper, so application serialization
  should not elevate them to the developer instruction hierarchy; a user-role
  envelope is the simplest supported lower-trust representation while preserving
  normal historical roles and explicit structured context. **Consequence:** The
  model still receives full normalized state and references, but prompt-like
  values cannot become privileged messages or alter the static instructions.
- **Decision 10 — Turn-local response IDs:** Keep
  `previous_response_id=None` on every new shopper turn and use IDs only for
  function outputs within that `run`. **Reason:** The backend, not provider
  retention, owns cross-turn state. **Consequence:** Session records never store
  OpenAI IDs and can be tested fully offline.
- **Decision 11 — Cross-turn grounding:** Historical constraints/prose/accepted
  IDs inform the model but never enter the current grounding set. **Reason:** An
  old card or model statement can be stale and cannot substitute for current
  commerce evidence. **Consequence:** A follow-up card requires a fresh
  qualifying current-turn tool result and Phase 5 re-fetch.
- **Decision 12 — Prompt version:** Bump to `phase6-v1`. **Reason:** The model's
  final schema, context input, and constraint-update duties materially change.
  **Consequence:** Every Phase 6 trace identifies the new behavior without
  storing prompt text.
- **Decision 13 — Trace resolved constraints:** Successful traces contain the
  complete post-merge state; failed traces contain the unchanged pre-turn
  snapshot. **Reason:** The trace should expose the application's actual state at
  the end of the attempted turn. **Consequence:** Evaluators need not infer
  retained state, but traces still are not the storage mechanism.
- **Decision 14 — Trace constraint changes:** Emit only actual semantic changes
  from the current successful patch, using old/new public projections; failures
  and no-ops emit none. **Reason:** Replayed full state and superficial
  normalization differences are not shopper-intent changes. **Consequence:** A
  field appears at most once per turn, in fixed contract order.
- **Decision 15 — In-memory/restart limitation:** State, locks, history, and
  counters live only in one app process and reset on app recreation/restart.
  **Reason:** Persistent/distributed sessions are explicit V1 non-goals.
  **Consequence:** Production multi-worker routing would require affinity or a
  later approved shared-state design.
- **Decision 16 — Failed turn indices:** Reserve indices before orchestration
  and never roll them back, while rolling back constraints/history.
  **Reason:** This preserves existing Phase 4/5 trace semantics and keeps every
  attempt uniquely ordered. **Consequence:** successful turn indices can contain
  gaps only when intervening failures occurred.
- **Decision 17 — Baseline integration gate:** Implement Phase 6 only after
  commit `4e7aa25` is in the target history. **Reason:** The active branch lacks
  the authoritative Phase 5 code this feature must extend. **Consequence:** Any
  merge/rebase discoveries are recorded here before Phase 6 source work begins.

## Risks and follow-ups

- **Model intent accuracy:** The model may miss or misclassify an explicit
  preference even with strict output. Deterministic merge prevents corruption
  from ambiguous patch mechanics but cannot prove semantic intent. Cover varied
  scripted behavior offline and use the external evaluation harness outside this
  repository for quality; do not add regex fallback extraction.
- **List replacement burden:** “Also” updates require the model to emit the
  complete new list for that field. If evaluation shows repeated loss, consider
  a separately planned add/remove list patch rather than silently changing these
  semantics.
- **Provider schema acceptance:** Offline tests prove generated structure but not
  deployed-model acceptance. The optional live smoke is the acceptance check;
  keep it manual and safe.
- **Context token growth:** Six full successful pairs plus fixed state are
  bounded but still add input tokens on every turn. Measure traces/evaluation
  before changing the bound or adding summarization.
- **Assistant prose trust:** Historical prose is context, not authority. It may
  contain stale or unsupported statements; deterministic commerce tooling and
  current grounding remain mandatory for new cards and commerce claims.
- **Prompt-shaped stored values:** Constraint strings ultimately originate in
  shopper input through the model. Treat the context JSON as data, retain
  read-only tools, and never let it control tool registries, code, commerce data,
  or hidden configuration.
- **Per-process session growth:** Per-session history is bounded, but the number
  of distinct session IDs is not evicted in V1. Add TTL/LRU/session-count policy
  only in a separately scoped production-readiness task with explicit semantics
  for reused IDs and active locks.
- **Long same-session latency:** Holding the session lock across provider I/O
  intentionally serializes a shopper's turns and may queue duplicate requests.
  Optimistic concurrency or idempotency keys are future API designs, not V1
  additions.
- **Multi-worker inconsistency:** In-memory state is not shared. Document single-
  process assumptions; do not imply cross-worker or restart persistence.
- **No session authentication:** Anyone who knows a session ID could submit a
  turn under this V1 contract. Real customer deployment requires an ownership
  boundary outside this phase.
- **Trace/state write atomicity:** Two separate in-memory repositories do not
  provide a general distributed transaction. The ordered, lock-held trace-then-
  state assignments remove ordinary fallible work before commit; catastrophic
  process failure/OOM between assignments remains a V1 limitation.
- **Missing product spec:** A later restored specification may define different
  normalization, history, or constraint semantics. Reconcile it before coding
  rather than changing an authoritative file.
- **Phase 5 branch divergence:** If Phase 5 is amended before integration, re-read
  its final code/tests and update this plan; do not assume commit `4e7aa25` is
  still the merge target.

## Outcome

Planning completed on 2026-09-05. No Phase 6 source, test, contract, fixture,
configuration, dependency, or runtime behavior has been implemented. This plan
defines the intended state architecture, strict patch, normalization and merge
rules, six-turn history, lower-trust user-role Responses context, transaction
boundary, per-session locking, current-turn recommendation grounding, trace
semantics, tests, and validation workflow. The pre-implementation architecture
review keeps static developer instructions as the only developer-role content;
shopper-derived resolved state is now a distinguished user-role data envelope.

Implementation remains gated on integrating the completed local Phase 5 branch
and rechecking any restored `docs/product-spec.md`. Complete this section with
shipped behavior, command results, live-smoke status, deviations, and remaining
limitations only after all milestones are implemented.
