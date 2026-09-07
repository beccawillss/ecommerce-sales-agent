# Shopper Web UI

## Goal

Phase 8 adds a polished, shopper-facing browser interface to the existing Sales
Agent application without changing the V1 chat contract or moving any commerce
authority into the browser. A visitor can open `GET /`, read a concise welcome
state, send natural-language messages, continue a multi-turn conversation using
the backend-issued `session_id`, and see assistant prose plus authoritative
structured product, promotion, and pricing data.

The finished experience has:

- one responsive outdoor-retail concierge page served by the existing FastAPI
  process;
- shopper and assistant messages, a text input, send button, Enter-to-send,
  starter prompts, a loading state, and a visible New conversation action;
- at most three product cards built only from `ChatResponse.recommendations`;
- promotion status built only from `ChatResponse.promotion` and one price quote
  associated with the matching card by `ChatResponse.pricing.product_id`;
- recommendation links that resolve at their existing authoritative
  `/products/...` paths to read-only, catalogue-backed local product pages;
- usable empty, unavailable, partial-stock, malformed-response, HTTP-error, and
  network-error states;
- keyboard, focus, semantic markup, contrast, and mobile behavior suitable for a
  portfolio demonstration;
- no direct OpenAI call, secret, trace viewer, commerce calculation, cart,
  checkout, or purchase mutation in browser code.

The observable request flow remains:

```text
browser GET /
    -> FastAPI-served HTML, CSS, and JavaScript

shopper submits text
    -> POST /api/v1/chat {message, session_id only when one is known}
    -> existing backend orchestration, commerce, state, hydration, and pricing
    -> ChatResponse
       -> message rendered as conversational text
       -> recommendations rendered as authoritative cards
       -> promotion rendered as validated status
       -> pricing attached to the exact product_id card
       -> returned session_id retained for the next browser turn
```

This phase is complete when the same FastAPI application serves the UI and
unchanged API, automated offline route/asset/API/security checks pass, the
manual browser acceptance checklist passes at desktop and mobile sizes, and an
optional credentialed multi-turn smoke demonstrates the Phase 7 promotion and
pricing flow without becoming a CI dependency.

## Context and authoritative sources

The implementation must be reconciled against these repository sources, in
precedence order:

- `AGENTS.md` defines the V1 trust boundary, backend-owned conversation state,
  Decimal-safe commerce rules, read-only capabilities, external evaluation
  boundary, test expectations, and non-goals.
- `.agent/PLANS.md` defines the structure and living-document rules for this
  ExecPlan.
- `contracts/salesagent_api_contract.yaml` defines the existing
  `POST /api/v1/chat` request and response. It is the browser's only application
  data API in Phase 8.
- `data/products.json` and `data/discounts.json` remain authoritative for product
  facts, relative product URLs, stock, promotion status, and percentages. The
  UI must never read these files or reproduce their rules.
- `src/salesagent/api/models.py` is the typed HTTP representation of the YAML
  contract. `ChatResponse` contains `session_id`, `trace_id`, `message`, zero to
  three recommendations, nullable singular promotion, and nullable singular
  pricing.
- `src/salesagent/api/routes/chat.py` exposes the shopper endpoint and converts
  terminal service failures to the generic safe HTTP 500 detail
  `Sales Agent is temporarily unavailable.`
- `src/salesagent/main.py:create_app` is the application composition root. It
  currently registers `/health`, the chat router, and the conditionally enabled
  evaluation trace router. It performs no network work during import.
- `src/salesagent/repositories/sessions.py` and
  `src/salesagent/domain/conversation.py` own process-local session state. A
  supplied non-empty ID that is not in the repository starts with a fresh empty
  `SessionState`; there is no session-existence or stale-session endpoint.
- `src/salesagent/services/chat.py` coordinates each turn and returns only
  backend-validated/hydrated cards and deterministic pricing. It preserves a
  supplied session ID or creates a UUID when the request omits it.
- `src/salesagent/services/recommendations.py` re-fetches and hydrates accepted
  products. Product-level availability is `in_stock`, `out_of_stock`, or
  `partial` for current valid catalogue data; `unknown` remains a contract value.
- `src/salesagent/services/pricing.py` validates current-turn promotion evidence
  and calculates a singular Decimal-safe quote for the first accepted
  recommendation. `ProductRecommendation.price` remains the catalogue base
  price; `PricingResult` carries the quote separately and identifies its target
  by `product_id`.
- `docs/plans/openai-agent-orchestration.md`,
  `docs/plans/recommendation-hydration.md`,
  `docs/plans/conversation-state.md`, and
  `docs/plans/promotion-pricing.md` record the completed Phase 4-7 design and
  the trust, failure, session, and quote semantics that the UI must preserve.
- `README.md`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, and all
  tests under `tests/` define the current Python-only setup and offline `quality`
  job. There is no Node package, frontend framework, template engine, JavaScript
  test runner, browser automation, or existing static directory.

`docs/product-spec.md` is named as authoritative by `AGENTS.md` but is absent
from the checkout inspected on 2026-09-07. No unavailable frontend or product
page requirement is assumed. If that file appears before implementation, read
it and reconcile any conflict in this plan before changing code.

The current public fields used by the UI are exactly:

```text
ChatRequest
    session_id: string | null, optional in JSON; non-empty when present
    message: string, 1..4000 and not whitespace-only in implementation

ChatResponse
    session_id: string
    trace_id: string
    message: string
    recommendations: ProductRecommendation[0..3]
    promotion: PromotionResult | null
    pricing: PricingResult | null

ProductRecommendation
    product_id: string
    name: string
    price: nonnegative number
    currency: "GBP"
    product_url: string
    availability: in_stock | out_of_stock | partial | unknown
    matched_variant: {colour, size, stock} | null

PromotionResult
    code: string
    valid: boolean
    discount_percent: number | null
    reason: string | null

PricingResult
    product_id: string
    base_price: nonnegative number
    final_price: nonnegative number
    currency: "GBP"
    discount_code: string | null
    discount_percent: number | null
```

Two final Phase 8 decisions resolve current implementation constraints without
an authoritative-contract change:

1. Session storage is process-local and the API has no stale-session signal.
   After an application restart, submitting an old browser `session_id` creates
   fresh backend state under that same ID and returns HTTP 200. The UI cannot
   reliably detect that reset. Phase 8 accepts this V1 behavior: it adds no
   expiry heuristic, state probe, or API field, and allows the backend to treat
   the retained ID as a fresh session. The UI explains the demo limitation and
   keeps New conversation as the explicit shopper reset.
2. Catalogue `product_url` values are authoritative same-origin relative paths
   such as `/products/apex-alpine`, but the current repository defines no
   `GET /products/{slug}` pages. Phase 8 will add the smallest read-only
   presentation route needed for those exact paths to resolve locally. It will
   resolve an existing product through `CommerceService`, render only escaped
   deterministic catalogue fields, and return 404 for an unknown or ambiguous
   path. It will not add a JSON endpoint, new commerce-domain capability, URL
   rewrite, model content, cart, checkout, or purchase action.

No other material conflict was found between the requested direction,
`AGENTS.md`, the current API contract, and the Phase 0-7 implementation.

## Scope

Phase 8 includes:

- a plain HTML document, one CSS file, and one JavaScript file stored with the
  `salesagent` Python package;
- FastAPI-native serving of `GET /` and a narrow static asset path from the
  existing application process;
- schema-hidden read-only HTML handling for the existing authoritative
  `/products/{slug}` paths, resolving products through the existing
  `CommerceService` and returning 404 when no unique exact URL match exists;
- a single-column chat experience with an outdoor-retail visual treatment,
  responsive recommendation grid, starter prompts, and accessible status copy;
- same-origin `fetch` calls only to `POST /api/v1/chat`;
- reuse of the backend-issued session ID within one browser tab through
  `sessionStorage`, with an in-memory fallback if storage is unavailable;
- a New conversation action that forgets the browser's ID and removes the
  rendered transcript without deleting or mutating server state;
- defensive decoding of the fields the UI displays, including finite,
  nonnegative numeric values and exact enum/currency checks;
- safe DOM construction for shopper messages, assistant messages, product
  fields, promotion fields, and links;
- card treatments for every contract availability value and nullable matched
  variants;
- exact `product_id` association for the singular structured quote;
- loading, duplicate-submit prevention, retryable failure presentation, and
  empty-assistant handling;
- no-dependency Python tests for routes, assets, headers, existing API/OpenAPI
  behavior, and static trust-boundary invariants;
- a documented manual browser checklist for interaction behavior that cannot be
  executed meaningfully in the existing Python-only test stack;
- README updates for opening the shopper UI, its process-local session
  limitation, and the optional live acceptance flow;
- updates to this ExecPlan while implementation proceeds.

Likely implementation files are:

```text
README.md
src/salesagent/main.py
src/salesagent/api/routes/ui.py                       # new root/product UI routes
src/salesagent/web/index.html                         # new
src/salesagent/web/static/app.css                     # new
src/salesagent/web/static/app.js                      # new
tests/test_ui.py                                      # new
tests/test_api.py                                     # existing OpenAPI regression coverage
docs/plans/shopper-web-ui.md                          # living plan
```

The exact Python route helper may stay in `main.py` if implementation proves a
separate file adds no clarity. The HTML, CSS, and JavaScript should remain
separate assets so browser caching, content types, and focused inspection are
straightforward. No template-engine dependency is needed: the chat shell is a
static file, while the small product document is assembled by a typed
presentation helper that escapes values from its resolved `Product`.

## Non-goals

Phase 8 does not add:

- React, Vue, Svelte, Vite, npm, a Node runtime/build chain, a template engine,
  a CSS framework, a frontend package manager, or a second runtime service;
- cart, basket, checkout, payment, ordering, purchase completion, refunds,
  returns, accounts, login, authentication, or customer data;
- product administration, promotion administration, catalogue mutation,
  inventory mutation, or any new agent tool;
- external storefront integration, a product JSON API, or invented fallback
  destinations for catalogue `product_url` values;
- invented images or recommendation-card attributes that do not exist in
  `ProductRecommendation`; the separate product page may display additional
  fields only from its resolved authoritative `Product`;
- browser reconstruction of resolved constraints, backend history, ranking,
  availability, promotion validity, discount percentages, base prices, final
  prices, or discount arithmetic;
- transcript synchronization with the backend, transcript persistence across a
  reload, permanent `localStorage`, cross-tab session sharing, accounts, or
  persisted/distributed server sessions;
- streaming, websockets, response cancellation, optimistic backend state,
  offline queuing, idempotency keys, or concurrent submissions;
- Markdown parsing, HTML rendering from the model, syntax highlighting, or
  model-authored links;
- direct OpenAI browser calls, exposure of `OPENAI_API_KEY`, prompt text,
  provider response data, raw traces, or the evaluation trace endpoint;
- a debug/trace panel, analytics, telemetry, service worker, deployment work,
  RAG, embeddings, vector search, another model provider, or the external
  evaluation harness;
- Playwright, Selenium, jsdom, or another browser-test framework added solely
  for this phase;
- changes to `contracts/salesagent_api_contract.yaml` or Phase 9 work.

## Current state

`src/salesagent/main.py:create_app` builds one FastAPI application titled
`Sales Agent` and registers these OpenAPI paths when traces are enabled:

```text
GET  /health
POST /api/v1/chat
GET  /api/v1/traces/{trace_id}
```

FastAPI's `/openapi.json`, `/docs`, and `/redoc` routes also remain available.
There is no `GET /`, no static mount, and no HTML response. The module-level
application imports successfully without an OpenAI key, and live model access
is lazy until chat.

The chat route accepts a Pydantic-validated `ChatRequest`, invokes synchronous
`ChatService.chat`, and either returns a `ChatResponse` or the fixed generic HTTP
500 detail. Request errors are FastAPI 422 responses. No CORS setup is needed
for a same-origin UI.

`ChatService` creates the first session ID when `session_id` is omitted or null.
Later requests preserve any supplied non-empty ID. Session state and the last
six successful turn pairs live in an `InMemorySessionRepository` attached to
that application instance. Same-session turns are serialized; failures consume
a trace turn index but do not update history or constraints. State disappears
on application recreation/restart and is not shared across workers.

The browser does not need and must not reproduce that state. Its only continuity
responsibility is to retain the returned opaque ID and include it on the next
request.

The successful response already gives the UI a clean authority split:

- `message` is conversational model prose and is display text only;
- `recommendations` contains backend-refetched canonical ID, name, catalogue
  price, GBP currency, catalogue URL, product-level availability, and an
  optional exact matched variant;
- `promotion` contains the canonical validated result for the nominated code,
  including negative active/unknown outcomes;
- `pricing` contains at most one application-calculated quote and names its
  product target explicitly;
- `trace_id` is not a shopper feature and has no UI use.

Phase 7 guarantees that structured pricing, when present, targets the first
accepted recommendation and agrees with the response/trace. The browser should
still validate the association defensively rather than depend on array position.
It must never calculate `final_price` from base price and percentage.

The project uses Python 3.13, FastAPI, Pydantic, OpenAI, and Uvicorn. Its dev
dependencies are pytest, HTTPX, Ruff, and mypy. The GitHub Actions `quality` job
runs the locked uv environment, pytest, Ruff lint/format, mypy, and an
application import. The current test suite is fully offline and already covers
the chat contract, generic 500, session reuse, structured cards, promotion,
pricing, OpenAPI, and trace gating.

## Proposed design

### Application and static asset serving

Keep one deployable application and use Starlette components already included
with FastAPI:

```text
FastAPI application
    GET /                         -> packaged index.html
    GET /products/{slug}          -> read-only catalogue product document
    /static/app.css               -> packaged stylesheet
    /static/app.js                -> packaged deferred script
    GET /health                   -> unchanged
    POST /api/v1/chat             -> unchanged
    GET /api/v1/traces/{trace_id} -> unchanged and conditionally gated
```

Resolve the asset directory relative to the installed `salesagent` package,
not the current working directory. Register a narrow `/static` `StaticFiles`
mount and a `GET /` handler returning `FileResponse`. Register the product
document route in the same UI router. Mark both HTML handlers
`include_in_schema=False`: they are human presentation routes, not part of the
YAML machine API, and excluding them keeps generated OpenAPI paths and operation
IDs stable. The static mount is not represented in OpenAPI.

Both HTML responses should set a small security header baseline without a new
middleware dependency:

```text
Content-Security-Policy:
  default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data:; connect-src 'self'; object-src 'none';
  base-uri 'none'; frame-ancestors 'none'; form-action 'self'
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
```

The document references only `/static/app.css` and `/static/app.js`; it uses no
inline scripts/styles, external font, CDN, tracker, or remote image. This makes
the CSP practical rather than decorative. Use system fonts and CSS-only
decoration.

The repository currently runs from source through uv. During implementation,
also verify that a built wheel contains the HTML/CSS/JavaScript. If uv's default
package inclusion omits them, add only the narrow build configuration needed to
include `src/salesagent/web/**`; do not add a frontend build tool or runtime
dependency. Record the finding in Discoveries.

### Read-only product presentation route

Add `GET /products/{slug}` as an HTML presentation route, not as a new public
JSON API or commerce capability. Pass the already assembled `CommerceService`
into the UI router from `create_app`; do not construct another repository, read
`data/products.json` in the route, call OpenAI, or add a product lookup rule to
JavaScript.

The current commerce service supports deterministic unfiltered catalogue search
and product lookup by ID but not lookup by URL. Keep URL resolution in the
presentation layer:

```text
requested_path = request.url.path
candidates = commerce_service.search_products(ProductSearchCriteria())
matches = [product for product in candidates
           if product.product_url == requested_path]

if exactly one match:
    render that Product at its existing product_url
else:
    return 404 "Product not found"
```

Use exact, case-sensitive path equality against `Product.product_url`. Do not
derive an ID from the slug, fuzzy-match names, redirect unknown slugs, or create
a fallback product. Treat multiple exact matches as ambiguous and fail closed
with 404; the current catalogue has unique URLs, and URL uniqueness is not being
added as a new domain invariant in this phase.

Render a small server-generated product document using a presentation helper and
`html.escape` (or an equivalently safe standard-library mechanism) for every
text value. Reuse the packaged stylesheet and the same security headers. The
page may display only values present on the resolved authoritative `Product`,
for example:

- name, category, base price, and currency;
- activities, weather, features, season, waterproof rating, and warmth;
- the exact colour, size, and stock values for each catalogue variant;
- a static link back to `/`.

Format the existing Decimal base price for display but perform no discount or
other commerce arithmetic. Do not include assistant prose, session state,
recommendation rationale, promotion/pricing claims, product imagery, cart,
checkout, payment, “buy” controls, or any POST action. The product document is
catalogue presentation at the product's existing authoritative URL and does not
claim to complete a purchase.

### Document and visual structure

Use semantic markup along these lines:

```text
body
  header
    Sales Agent / outdoor concierge identity
    New conversation button
  main
    introduction and process-local demo note
    conversation log (aria-live="polite")
      welcome/empty state and optional starter prompts
      shopper/assistant message groups
      recommendation cards associated with an assistant turn
      promotion status associated with that assistant turn
    request status (role=status)
  form
    labelled textarea, character affordance if useful, Send button
```

Use a restrained palette inspired by forest, stone, sky, and warm canvas rather
than image-heavy branding. Keep the readable content width bounded on desktop;
use a one-column layout on small screens and an auto-fitting card grid at wider
sizes. The composer remains visible without covering content, and controls have
comfortable touch targets. Avoid animation beyond a subtle loading indicator;
respect `prefers-reduced-motion`.

The empty state should explain what the concierge can help with and may offer
three static starter prompts. Selecting one copies that known static text into
the composer and focuses it; submission remains an explicit shopper action.
Once the first message is appended, remove the welcome panel. A successful turn
with no recommendations is normal: show its assistant message and omit the card
grid rather than claiming that a product search failed.

No product imagery should be invented because `ProductRecommendation` has no
image field. Visual polish comes from typography, spacing, badges, and layout.

### Browser state and session flow

Keep one opaque browser value under a versioned key such as
`salesagent.session_id.v1`:

```text
on startup:
    try sessionStorage.getItem(key)
    accept only a nonblank string, otherwise use null
    if storage throws, continue with an in-memory null/string variable

on submit:
    payload = {message: exact textarea value}
    if session_id is nonnull: payload.session_id = session_id
    POST payload to /api/v1/chat

on valid success:
    if an existing session was sent, require returned session_id to match it
    otherwise accept the returned nonblank session_id
    update in-memory session_id
    try sessionStorage.setItem(key, session_id)

on New conversation:
    require no request in flight
    set in-memory session_id = null
    try sessionStorage.removeItem(key)
    clear the rendered transcript and transient error/status
    restore the welcome state and focus the composer
```

Do not generate a client session ID. Do not store `trace_id`, resolved
constraints, promotion evidence, pricing inputs, provider data, or raw API
responses. Keep the rendered transcript in DOM memory only. Consequently, a
page reload within the same tab preserves backend continuity through the ID but
does not reconstruct earlier bubbles. The page should state this succinctly if
it starts with a stored ID, for example “Conversation context is retained for
this browser tab; earlier messages are not shown after a reload.”

New conversation is intentionally a local forget operation, not a server delete.
The old process-local backend record remains unreachable from this tab unless
its ID is supplied again. Disable New conversation while a request is active so
a late response cannot repopulate an ID after reset.

There is no reliable stale-session handshake. An old ID submitted after server
restart is accepted as a fresh backend session with the same string. The UI
should include an unobtrusive demo note that server restarts reset conversational
memory and advise using New conversation if context appears lost. It must not
automatically clear an ID on HTTP 500 or guess from assistant prose.

### Chat submission state machine

Use one explicit `requestInFlight` boolean and one form submit handler for both
the Send button and Enter key:

```text
idle
    blank/whitespace-only -> do not submit; keep focus and expose validation
    >4000 characters      -> prevented by maxlength and checked again in JS
    valid submit          -> append shopper bubble, clear old error,
                             set inFlight, disable Send/New conversation,
                             set aria-busy/status, call fetch

success with valid JSON
    render assistant turn and structured data
    commit returned session ID
    clear composer/draft
    clear inFlight and restore focus

HTTP/network/JSON/schema failure
    render a safe accessible error attached to the failed turn
    restore the submitted text to the composer when it is still empty
    mark the shopper message as not answered/retryable
    never show response body, provider category, stack, or raw exception
    clear inFlight and restore controls/focus
```

Check `requestInFlight` at the top of the handler as well as disabling controls;
this closes keyboard/double-click races. The textarea handles Enter as submit
and Shift+Enter as a newline. Do not register a second key path that bypasses
the form's guard.

Append the shopper bubble before awaiting the response so the action is visible.
Do not append it twice on a retry; either reuse/replace the marked failed bubble
or remove the failed marker before the next attempt. Because the API has no
idempotency key, a network failure can be ambiguous: the server might have
completed the turn after the connection was lost. Do not automatically retry.
Keep the draft and let the shopper choose to resend, with concise copy such as
“We couldn't confirm the response. Review your message before trying again.”

For a known HTTP 500, use a shopper-safe message such as “The concierge is
temporarily unavailable. Your message is still here—please try again.” Do not
surface `detail`. Handle 400/422 as a generic request problem; normal UI
validation should prevent them. A response with an unexpected content type,
invalid JSON, or invalid displayed field is “an unexpected response,” not an
internal diagnostic.

If a schema-valid response contains an empty/whitespace-only `message`, render a
neutral assistant bubble such as “No conversational message was returned.” and
continue to show valid structured cards. Do not fill it with inferred product or
promotion prose.

### Defensive response decoding

Keep a small, explicit JavaScript decoder next to rendering code. It is not a
second source of commerce truth and should not replicate every Pydantic rule;
it verifies that values are safe and meaningful for the elements the UI will
create.

Before changing browser session state or rendering structured data, require:

- a top-level object with nonblank string `session_id` and `trace_id`, string
  `message`, an array `recommendations` with at most three items, and
  `promotion`/`pricing` that are object-or-null;
- every recommendation to have nonblank string ID/name/URL, finite nonnegative
  numeric price, currency exactly `GBP`, a known availability enum, and a valid
  object-or-null matched variant;
- matched variant colour/size strings and finite nonnegative integer stock;
- promotion code string, boolean validity, nullable finite 0..100 percent, and
  nullable string reason;
- pricing product ID, finite nonnegative numeric base/final prices, currency
  exactly `GBP`, nullable code, and nullable finite 0..100 percent;
- a pricing product ID that exactly matches one recommendation ID; pricing
  without a matching card is not displayed as a standalone quote;
- when pricing exists, a non-null valid promotion and compatible structured code
  fields. Do not derive a missing code or percentage from another field.

Reject duplicate recommendation IDs as an unexpected response because pricing
association would be ambiguous. Do not accept a new successful response whose
`session_id` differs from the existing ID sent with the request. These checks
should fail closed with the generic UI error, not try to repair backend data.

The decoder must not query product fixtures, infer stock from matched variants,
check a percentage formula, or calculate a final price. JavaScript numbers are
used only to validate the JSON boundary and format already-authoritative values
for display with `Intl.NumberFormat`; they are never authoritative arithmetic.

### Safe text and link rendering

Construct all dynamic elements with `document.createElement`, set text with
`textContent`, and attach events with `addEventListener`. Clearing may use
`replaceChildren()` with trusted DOM nodes. Do not use `innerHTML`,
`insertAdjacentHTML`, `document.write`, `eval`, dynamic script construction, or
an HTML/Markdown parser for shopper, assistant, product, promotion, pricing, or
error content.

Assistant line breaks may be preserved with CSS `white-space: pre-wrap`; no
markup interpretation is necessary. Shopper text receives the same treatment.

Create the View product anchor from `recommendation.product_url` only. Parse it
against `window.location.origin`, permit only `http:` and `https:` destinations,
and reject credentials or another executable scheme. Preserve the authoritative
resolved target; do not use a URL found in assistant prose. The current fixture
URLs are same-origin relative `/products/...` paths handled by the read-only
product presentation route. Open product links in a new tab with
`target="_blank"` and `rel="noopener noreferrer"` so the DOM-only chat transcript
is not discarded. Use accurate accessible copy such as “View product (opens in
a new tab),” not “Buy now” or “Added to cart.”

### Recommendation, availability, and variant presentation

For each recommendation, render only:

- name;
- catalogue price formatted from `price` and `currency`;
- an availability badge mapped from the structured enum;
- matched colour, size, and stock only when `matched_variant` is non-null;
- the authoritative View product link.

Use fixed UI labels rather than exposing raw enum values:

```text
in_stock     -> In stock
partial      -> Some variants available
out_of_stock -> Out of stock
unknown      -> Availability not confirmed
```

Out-of-stock cards remain visible because the backend deliberately recommended
them and the availability is useful context; visually de-emphasize their action
without disabling the authoritative product link. `partial` must not be relabelled
as fully in stock. `unknown` must not imply availability. A matched variant is
additional structured evidence, not a reason to recalculate the card's
product-level status.

If `recommendations` is empty, render no placeholder/fake card. The assistant
message remains the explanation, and the welcome state covers the pre-chat empty
experience.

### Promotion and singular pricing presentation

Treat promotion and pricing as one structured presentation attached to an
assistant turn:

- when `promotion.valid` is true, show the canonical code and validated percent
  when it is present;
- when it is false, map known reasons `inactive` and `unknown_code` to clear
  shopper copy and show no discounted price;
- when it is valid but `pricing` is null, present it as a validated code without
  claiming it has been applied to a product;
- when it is absent, render no promotion badge even if assistant prose mentions
  a code;
- never derive promotion state from the code's spelling or from card data.

Build a map of rendered cards by exact `product_id`. When pricing is present,
look up `pricing.product_id` and add a quote block inside only that card. Display
`pricing.base_price` as the original quoted amount and `pricing.final_price` as
the final amount, with `discount_code`/`discount_percent` only when structured
values are present. The base catalogue `recommendation.price` remains available
as the normal card price, but no browser subtraction, multiplication, rounding,
or equality repair occurs.

Do not attach pricing to index zero merely because the current backend normally
targets the first card. Exact ID linkage is the UI rule. If the association is
missing or ambiguous, treat the response as unexpected and display no quote.

### Accessibility and responsive baseline

Implementation and manual review must include:

- one logical heading hierarchy, semantic `main`, `form`, buttons, links, and
  `article`/list treatment for messages and cards;
- a persistent programmatic label for the textarea rather than placeholder-only
  identification;
- a polite live region for new assistant turns/loading and an assertive or
  `role="alert"` region for failures without duplicating announcements;
- `aria-busy` during a request and native `disabled` controls for unavailable
  actions;
- visible `:focus-visible` outlines with adequate offset, keyboard access to
  starter prompts/New conversation/product links, and Shift+Enter support;
- contrast suitable for normal and muted text; availability must not depend on
  colour alone;
- minimum practical touch targets, a viewport meta tag, no horizontal overflow,
  and usable layouts around 320px width through desktop;
- no focus theft while the shopper is typing; after submit completion/reset,
  focus returns deliberately to the composer;
- reduced-motion behavior and no required hover interaction.

Use progressive enhancement only within this single script. With JavaScript
disabled the document may show the brand and explanation, but chat cannot work;
a no-script message should say that JavaScript is required for this demo.

### Documentation and CI

Update `README.md` to make `http://127.0.0.1:8000/` the shopper entry point while
retaining the health/API/trace descriptions. Document that:

- live chat still requires `OPENAI_API_KEY`;
- session continuity is backend-owned, process-local, and single-process;
- the browser stores only the issued ID for the current tab/session;
- reload does not reconstruct the visual transcript;
- New conversation forgets the browser ID but does not delete a server record;
- stale retained IDs are accepted as fresh sessions after backend state loss,
  with no expiry heuristic or hidden probe;
- product links use authoritative fixture URLs that resolve to local read-only
  catalogue pages, while checkout and purchase remain unsupported.

Do not change the GitHub Actions workflow merely to add a frontend stage. New
FastAPI/static tests run naturally in the existing pytest step, and source
inspection fits pytest without a Node install. The current Ruff, format, mypy,
and import steps remain the quality gate.

## Milestones

### Milestone 1 — Serve the packaged UI shell

#### Outcome

Opening `/` returns the branded semantic document, its CSS and JavaScript load
from the existing FastAPI process, every authoritative product URL resolves to a
read-only catalogue page, unknown product paths return 404, existing
API/docs/health/trace routing still works, and HTML documents have the planned
security headers.

#### Implementation

- Add `src/salesagent/web/index.html`, `web/static/app.css`, and
  `web/static/app.js` with the base landmarks, welcome state, composer, status
  regions, and responsive visual system.
- Add the root route and narrow `/static` mount in the application composition,
  resolving paths relative to the package and excluding presentation routes from
  OpenAPI.
- Add `/products/{slug}` to the same UI router, inject the existing
  `CommerceService`, resolve by exact authoritative `product_url`, and render
  escaped catalogue-only HTML without adding a product API or commerce method.
- Add `tests/test_ui.py` route/asset/content-type/header/404 coverage.
- Verify built-package inclusion and make only a narrow packaging metadata
  adjustment if required.

#### Validation

```bash
uv run pytest tests/test_ui.py tests/test_health.py tests/test_api.py
uv run python -c "from salesagent.main import app; print(app.title)"
```

Success means `/`, every current catalogue `product_url`, and both named assets
are 200 with expected content types; unknown product paths/assets remain 404;
product pages contain authoritative escaped values and no mutation controls;
CSP/security headers are present; the app imports as `Sales Agent`; and
pre-existing endpoints retain their behavior.

### Milestone 2 — Implement chat and browser session interaction

#### Outcome

A shopper can submit one or more messages, see ordered bubbles/loading state,
reuse the returned session ID, avoid duplicate requests, recover a draft after
failure, and start a fresh browser conversation.

#### Implementation

- Implement guarded form submission, Enter/Shift+Enter behavior, same-origin
  fetch, safe response/error handling, focus restoration, and message rendering.
- Implement the versioned `sessionStorage` adapter with in-memory fallback,
  response ID consistency checks, and no client-generated ID.
- Implement New conversation as an idle-only local reset of ID, transcript,
  errors, and welcome state.
- Add the process-local/reload note and keep the evaluation trace ID unused.

#### Validation

```bash
uv run pytest tests/test_ui.py tests/test_api.py
```

Then perform the offline scripted manual interaction cases in the Test plan.
Success means one request is active at a time, the second request includes the
first valid response's ID, failures do not expose response details or erase the
draft, and reset causes the next request to omit `session_id`.

### Milestone 3 — Render authoritative recommendations and quotes

#### Outcome

Structured response data produces up to three accessible cards with correct
availability/variant treatment, authoritative links that resolve to local
catalogue pages, promotion status, and a singular quote on the exact matching
product.

#### Implementation

- Add the narrow response decoder and fail-closed malformed-response path.
- Build messages/cards/badges/links entirely with DOM APIs and `textContent`.
- Format backend numeric values for GBP display without discount arithmetic.
- Map all four availability values and nullable matched variants.
- Map valid/inactive/unknown promotion results and attach pricing by exact
  `product_id` only.
- Open structured product links safely in a new tab and verify the destination
  displays only the matching deterministic `Product` fields.
- Add test source invariants and representative fixture responses for manual
  checks, without copying production catalogue data into UI logic.

#### Validation

```bash
uv run pytest tests/test_ui.py tests/test_api.py tests/test_pricing.py tests/test_recommendations.py
```

Manual fixtures must show all availability states, zero-card behavior, valid and
invalid promotions, valid-without-pricing, exact price-to-card association, and
rejection of an unmatched pricing product ID. Inspect the rendered anchors to
confirm they come from structured `product_url`, never assistant text, and that
each current destination returns its matching catalogue page rather than 404.

### Milestone 4 — Complete accessibility, errors, and responsive behavior

#### Outcome

The demo is usable with keyboard and common mobile/desktop viewports; loading,
HTTP, network, malformed, empty-message, and process-restart limitations are
clear without exposing internals.

#### Implementation

- Complete focus-visible, contrast, live-region, `aria-busy`, disabled-state,
  reduced-motion, touch-target, text-wrap, and narrow-screen styling.
- Verify the in-flight guard across click and keyboard paths.
- Finalize safe error copy, failed-message/draft retry treatment, and empty
  assistant fallback.
- Verify the process-local memory note and New conversation recovery path.

#### Validation

Run the manual accessibility/responsive/error checklist under the Test plan in
current Chrome/Chromium or Firefox using keyboard-only interaction and responsive
device emulation. Automated route and source-safety tests must still pass.

### Milestone 5 — Lock API regressions and documentation

#### Outcome

Phase 8 is documented, the public V1 chat/trace contract remains unchanged,
generated OpenAPI retains existing machine paths and schemas, and the complete
offline quality job passes without Node or OpenAI access.

#### Implementation

- Extend existing API regression tests only where needed to prove the UI route
  does not change chat/trace request, response, operation, trace-gating, or schema
  behavior.
- Keep root/static paths outside OpenAPI and add no CORS or frontend API.
- Update README setup/run/session/product-link documentation.
- Update Progress, Discoveries, Decision log, and risks in this plan.

#### Validation

Run every command in Validation commands. Compare the relevant generated
OpenAPI request/response schemas and existing operation IDs with
`contracts/salesagent_api_contract.yaml`; successful comparison requires no YAML
edit.

### Milestone 6 — Manual live shopper acceptance

#### Outcome

When credentials are available, the actual browser UI completes a three-turn
OpenAI-backed concierge conversation and presents only structured authoritative
commerce data. Without credentials, the check is explicitly recorded as not run
and does not block offline CI.

#### Implementation

- Start the existing Uvicorn application with `OPENAI_API_KEY` configured.
- Complete the live scenario in the Test plan in a browser.
- Record date, result, model/prompt version if safely available through existing
  developer diagnostics, and any deviation in Outcome. Do not add trace display
  to the shopper UI.

#### Validation

The scenario passes only when the same browser session continues all three
turns, one authoritative recommendation card appears, WELCOME10 status is
structured, pricing is on the correct card, link/availability fields match the
chat JSON, duplicate submission is prevented, and no product/promotion/price
data is parsed from prose. This check is manual, potentially billable, and must
never run in CI.

## Test plan

### Automated FastAPI and asset tests

Add `tests/test_ui.py` using `fastapi.testclient.TestClient` and the existing
injectable application factory. Cover:

- `GET /` returns 200 HTML with `lang`, viewport metadata, one main heading,
  labelled composer/form, New conversation, status/error live regions,
  no-script notice, and same-origin CSS/JS references;
- the root document sends the CSP, referrer, and content-type protection headers;
- `/static/app.css` and `/static/app.js` return 200 with correct media types;
- a nonexistent static asset returns 404 and never falls back to index HTML;
- every `Product.product_url` returned by the real deterministic commerce service
  returns 200 HTML at that exact path, contains the matching escaped catalogue
  name/base price/currency and variant data, and requires no OpenAI key or call;
- an unknown `/products/...` path and an ambiguous URL resolution return 404,
  with no fuzzy match, redirect, or substitute product;
- the product renderer escapes synthetic HTML-shaped catalogue values, and
  product pages contain no chat/model prose, cart, checkout, payment, purchase
  form, POST action, or model/trace request;
- the HTML has no inline script/event handler and references no remote font,
  script, stylesheet, tracker, or OpenAI host;
- the JavaScript source contains no `innerHTML`, `insertAdjacentHTML`,
  `document.write`, `eval`, `OPENAI_API_KEY`, OpenAI endpoint, or trace endpoint;
- the script's only application request path is `/api/v1/chat` and it contains
  no catalogue fixture IDs, promotion fixtures, discount formula, or product
  URL fallback.

Static source assertions are narrow trust-boundary regression checks, not a
substitute for browser behavior tests. Avoid brittle snapshots of all styling or
copy.

### Existing API and OpenAPI regression tests

Retain and, where useful, strengthen `tests/test_api.py` to prove:

- chat still accepts only the existing request shape and returns the existing
  response shape;
- a supplied session ID is preserved and an omitted/null ID is generated;
- recommendation, promotion, and pricing structures remain unchanged;
- generic HTTP 500 behavior remains safe;
- trace enable/disable behavior remains unchanged;
- OpenAPI retains `/health`, `/api/v1/chat`, and the conditional trace path,
  existing operation IDs, required fields, recommendation max length,
  availability enum, numeric API money, and singular nullable promotion/pricing;
- `GET /`, `GET /products/{slug}`, and the static mount are excluded from
  OpenAPI.

No test calls OpenAI. Continue using `ScriptedResponsesClient` for application
integration and the real deterministic commerce services where relevant.

### Manual offline browser checks

The repository has no JavaScript runner, DOM implementation, or browser
automation. Do not add a heavy tool solely for Phase 8. Run these checks against
locally controlled responses or an injected/scripted development application:

1. Submit by Send and Enter; verify Shift+Enter inserts a newline.
2. Double-click Send and press Enter repeatedly while loading; verify one network
   request and disabled Send/New conversation controls.
3. Complete two turns; verify the second JSON request contains the first
   response's exact `session_id` and no resolved constraints/transcript/trace.
4. Reload the tab; verify the ID remains in `sessionStorage`, old bubbles are not
   reconstructed, and the continuity notice is accurate.
5. Choose New conversation; verify the ID and transcript clear and the next
   request omits `session_id`.
6. Simulate storage access throwing; verify in-memory multi-turn behavior still
   works for the page lifetime.
7. Simulate network failure, HTTP 500, 422, non-JSON, malformed fields, duplicate
   IDs, mismatched returned session ID, and unmatched pricing product ID; verify
   safe copy, retained draft, usable controls, and no raw response detail.
8. Return an empty assistant message with valid structured cards; verify the
   neutral fallback and cards appear.
9. Render responses covering no cards, `in_stock`, `partial`, `out_of_stock`,
   `unknown`, and a matched variant; verify exact labels and no inferred facts.
10. Render active promotion with pricing, active promotion without pricing,
    inactive promotion, unknown code, and no promotion; verify only structured
    values appear and the quote attaches by exact product ID.
11. Put HTML, a script tag, Markdown link syntax, and a fake URL in shopper and
    assistant text; verify literal text rendering and no created node/link/script.
12. Follow each rendered View product link; verify it opens a new tab at the
    exact structured `/products/...` URL, returns 200, shows matching catalogue
    facts/variants, and offers no cart, checkout, payment, or purchase mutation.
    Enter an unknown product path directly and verify a 404 response.
13. Use keyboard-only navigation, 200% zoom, a roughly 320px viewport, and a
    desktop viewport; verify visible focus, logical order, announcements,
    readable contrast, no content loss, and no horizontal overflow.
14. Restart the application while the browser retains an old ID; verify the next
    request sends that ID, the backend accepts it as a fresh session, the UI adds
    no expiry warning/probe and makes no false detection claim, and New
    conversation remains the explicit recovery/reset action.

Record the browsers/viewports checked in Outcome. If Phase 8 later gains a
lightweight established JavaScript test setup for another reason, move decoder,
session, rendering, and state-machine cases into that runner; do not introduce
one pre-emptively.

### Manual live OpenAI-backed acceptance

After the offline quality gate passes and only when developer credentials are
available:

```bash
OPENAI_API_KEY=... uv run uvicorn salesagent.main:app --reload
```

Open `http://127.0.0.1:8000/` and submit:

```text
Turn 1: I need a waterproof hiking jacket under £160.
Turn 2: I'd prefer blue.
Turn 3: Actually make my budget £120 and I have WELCOME10.
```

Verify:

- one browser `session_id` is reused on Turns 2 and 3;
- message ordering, loading, focus, and duplicate-submit prevention are correct;
- the backend retains/adds/replaces constraints even though the browser neither
  stores nor sends them;
- the final accepted card's ID/name/base price/currency/availability/URL exactly
  match structured `ChatResponse.recommendations`;
- following the card link opens the exact authoritative URL in a new tab, returns
  a non-404 local product page, and shows catalogue facts for that same product;
- the canonical WELCOME10 result comes from `promotion`;
- original/final prices come from `pricing` and render on the card with the same
  `product_id`;
- no card, link, promotion, percentage, or price is derived from assistant prose;
- New conversation clears the browser ID/transcript and a subsequent request
  omits the ID;
- after a deliberate backend restart, the retained ID is submitted unchanged and
  accepted as fresh backend state without a heuristic probe or new API field;
- no API key, hidden instruction, raw trace, tool payload, provider detail, or
  model reasoning is visible in page source, storage, or shopper UI.

The check may incur API cost. It is never a pytest/CI command. Do not use the
shopper UI to fetch raw traces; existing safe developer diagnostics may be used
separately if a failure needs classification.

## Security and trust-boundary checks

- **Model prose is text only:** Shopper and assistant messages are assigned to
  `textContent` and never interpreted as HTML, Markdown, a URL, CSS, or script.
- **Product facts stay authoritative:** Cards read only the structured
  recommendation object returned by the backend. The UI does not read fixtures,
  tool results, trace data, or prose for product fields.
- **Product IDs stay backend validated:** The browser does not nominate, repair,
  canonicalize, or substitute IDs. It uses IDs only to key rendered cards and
  associate the singular quote.
- **Prices and discounts stay deterministic:** The browser formats supplied
  numeric values but performs no discount, rounding, eligibility, comparison,
  or final-price calculation. Pricing is never moved to another card.
- **Availability stays authoritative:** Fixed labels map only the response enum;
  variant stock is displayed but never used to recalculate the product status.
- **Links stay structured:** Only `ProductRecommendation.product_url` can create
  a product anchor, and executable/credential-bearing schemes are rejected.
  Model-written links remain inert text. Current authoritative paths resolve
  through the read-only product presentation route rather than a model or
  browser lookup.
- **Product pages stay catalogue-backed:** The product route receives the
  existing `CommerceService`, matches the exact authoritative `product_url`,
  escapes every rendered field, and returns 404 when no unique existing product
  matches. It never consumes model prose, session state, traces, or browser
  claims and exposes no mutation action.
- **Tools and OpenAI remain server-side:** JavaScript calls only the same-origin
  chat API. It contains no key, SDK, model endpoint, prompt, tool schema, or
  commerce service logic.
- **Session state stays backend-owned:** The browser stores one opaque ID only;
  it never stores or submits resolved constraints as authority. Backend state is
  process-local and may reset independently. Phase 8 intentionally adds no
  expiry heuristic, hidden probe, or contract field; an unknown retained ID is
  allowed to become a fresh backend session.
- **Trace surface stays evaluation-only:** The shopper UI neither calls nor
  links the trace endpoint and never stores `trace_id`. Existing route gating is
  unchanged.
- **Errors stay safe:** The UI maps HTTP/network/decoding failures to fixed
  shopper copy and never renders raw response bodies, exception messages,
  headers, or provider categories.
- **Static document gets a restrictive policy:** Same-origin assets/API and the
  planned CSP reduce script/style injection exposure without an external
  dependency.
- **No mutation or false purchase:** The only browser application request is
  chat interaction; product links and product pages are GET-only presentation,
  not cart/order actions, and copy does not claim a transaction succeeded.
- **No evaluation hard-coding:** Starter prompts and manual acceptance examples
  are demo affordances/tests only. Production browser code contains no scenario
  IDs, golden routing, product-ID special cases, or promotion-code rules.

## Validation commands

Run from the repository root during and after implementation:

```bash
uv sync
uv run pytest tests/test_ui.py tests/test_api.py tests/test_health.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -c "from salesagent.main import app; print(app.title)"
git diff --check
```

Successful output means the locked environment needs no unplanned dependency;
UI/static and all Phase 0-7 tests pass without external network access; lint,
format, and strict typing checks pass; importing the application without an API
key prints `Sales Agent`; generated API behavior remains compatible with the
unchanged YAML contract; and the diff has no whitespace errors.

Also run a package-content check after the assets exist:

```bash
uv build
```

Inspect the resulting wheel and confirm it contains
`salesagent/web/index.html`, `salesagent/web/static/app.css`, and
`salesagent/web/static/app.js`. Build output belongs under ignored build
artifacts and must not be committed. If a canonical packaging check is added to
the repository later, replace this manual inspection with it.

The existing GitHub Actions `quality` job must pass unchanged. Do not add an
OpenAI key, network request, paid test, Node installation, or browser download
to CI.

After the offline checks, the optional manual live acceptance uses:

```bash
OPENAI_API_KEY=... uv run uvicorn salesagent.main:app --reload
```

Record it as not run when credentials are unavailable. Never imply that offline
tests prove deployed-model behavior; local product-route tests prove only the
current deterministic catalogue destinations.

## Progress

- [x] 2026-09-07: Read the Phase 8 brief, `AGENTS.md`, `.agent/PLANS.md`, the
  complete API contract, README, completed Phase 4-7 plans, current Phase 0-7
  implementation, test organization, project configuration, and CI workflow.
- [x] 2026-09-07: Inspected current FastAPI routes/OpenAPI, dependency/tooling
  baseline, structured recommendation/promotion/pricing shapes, process-local
  session behavior, and authoritative relative product URLs.
- [x] 2026-09-07: Authored this planning-only ExecPlan. No application, test,
  dependency, workflow, contract, fixture, or README change was made.
- [x] 2026-09-07: Confirmed the unchanged Phase 0-7 offline baseline with
  `uv run pytest` (247 passed) and checked the new plan for whitespace errors.
- [x] 2026-09-07: Finalized the pre-implementation decisions: stale retained
  IDs are accepted as fresh V1 backend sessions without heuristics/probes, and
  authoritative product URLs receive a catalogue-backed read-only local HTML
  route with unknown paths returning 404. No implementation was started.
- [ ] Milestone 1 — Serve the packaged UI shell.
- [ ] Milestone 2 — Implement chat and browser session interaction.
- [ ] Milestone 3 — Render authoritative recommendations and quotes.
- [ ] Milestone 4 — Complete accessibility, errors, and responsive behavior.
- [ ] Milestone 5 — Lock API regressions and documentation.
- [ ] Milestone 6 — Complete or explicitly defer manual live acceptance.

## Discoveries

- `GET /` is currently unclaimed, while FastAPI's docs and the three application
  endpoints already have stable routes. This matters because the UI can use the
  natural root without changing an existing endpoint or adding a service.
- The repository has no frontend source, Node manifest, JavaScript runner,
  browser automation, template engine, or remote asset dependency. This matters
  because plain packaged HTML/CSS/JavaScript is both the smallest implementation
  and the approach least likely to disrupt the current offline quality job.
- FastAPI already brings Starlette `StaticFiles` and `FileResponse`. This matters
  because serving a document and two assets requires no new runtime dependency.
- Generated OpenAPI currently exposes `/health`, `/api/v1/chat`, and the enabled
  trace path, plus FastAPI's separate docs routes. This matters because marking
  `GET /` out of schema and using a static mount can preserve the machine API
  surface exactly.
- `ChatResponse` already contains every requested UI commerce field. This matters
  because Phase 8 should be a pure API consumer and needs no contract or backend
  response extension.
- `ProductRecommendation` has no image, description, feature list, or purchase
  status. This matters because polished cards must not fill visual gaps by
  parsing prose or importing fixture facts.
- Phase 5 currently emits `matched_variant=null`, but the public contract permits
  a structured variant. This matters because the UI can implement the nullable
  presentation now without assuming current cards always have a variant.
- Phase 7's singular `PricingResult` identifies one product and currently targets
  the first accepted recommendation. This matters because the UI must associate
  it by exact `product_id`, not by array position or discount calculation.
- Negative promotions are successful HTTP 200 business results with structured
  `valid=false` and no pricing. This matters because the browser must present
  them as useful validation outcomes, not network errors.
- The API returns `trace_id` on successful chat, but traces are an evaluation
  surface and may be disabled. This matters because a shopper UI has no reason
  to store, fetch, or expose the ID.
- The backend accepts any non-empty supplied `session_id`; absence from the
  in-memory repository is indistinguishable from a legitimate fresh empty
  session. This matters because stale-session auto-detection is impossible under
  the unchanged contract and would be misleading.
- Backend state, locks, turn counters, and history reset on app recreation and
  are not shared across workers. This matters because an old browser ID may
  survive longer than its backend state and the UI must document, not conceal,
  that demo limitation.
- Catalogue product URLs are relative `/products/...` paths and no product page
  route exists yet. This matters because Phase 8 must add an exact-path,
  read-only presentation route before recommendation links can ship without
  local 404s; the route can reuse `CommerceService` without changing the public
  API or commerce domain.
- `CommerceService` can return the complete catalogue through an unfiltered
  `ProductSearchCriteria`, while `Product` carries its authoritative URL and all
  deterministic display fields. This matters because presentation-layer exact
  URL resolution needs neither a new repository method nor a new public product
  endpoint.
- Browser interaction logic cannot be executed by pytest without adding a
  JavaScript runtime/DOM or browser framework that the repository does not have.
  This matters because route, API, and source safety receive automated coverage,
  while interaction/accessibility/responsive behavior needs an explicit manual
  checklist for V1.
- A network failure after POST is inherently ambiguous because the API has no
  idempotency key. This matters because automatic retry could create a duplicate
  backend turn; the UI should preserve the draft and let the shopper decide.
- The application currently resolves catalogue fixtures from repository root,
  while new UI assets should resolve from the Python package. This matters for
  running from different working directories and requires a wheel-content check.

## Decision log

- **Decision 1 — Frontend technology choice:** Use plain semantic HTML, CSS, and
  dependency-free JavaScript served by the existing FastAPI application.
  **Reason:** The current repository is Python-only, the interaction is small,
  and no component/build ecosystem is needed for one page. **Consequence:** No
  React/Vite/Node dependency or second service is introduced; complex browser
  interaction receives manual acceptance coverage.
- **Decision 2 — Static asset/FastAPI serving design:** Serve packaged
  `index.html` at schema-hidden `GET /`, mount only the packaged `static`
  directory at `/static`, and register the schema-hidden read-only product HTML
  route in the same FastAPI UI router. Resolve assets from the installed package
  and verify wheel contents. **Reason:** This is the narrowest same-origin design
  and preserves current API/OpenAPI behavior. **Consequence:** the application
  remains one process and needs no CORS, template engine, or runtime service.
- **Decision 3 — Browser session ID storage strategy:** Store only the nonblank
  backend-returned `session_id` in versioned `sessionStorage`, with an in-memory
  fallback when storage throws. **Reason:** It preserves same-tab continuity
  without permanent tracking or frontend-owned conversation state.
  **Consequence:** reload retains backend context but not the rendered transcript;
  closing the tab/browser session forgets the ID.
- **Decision 4 — New-conversation/reset behavior:** While idle, remove the
  browser ID, transcript, errors, and transient status, restore the welcome
  state, and focus the composer; do not call a delete endpoint. **Reason:** No
  server mutation exists or is needed. **Consequence:** the next POST omits
  `session_id`, while the old process-local record remains until restart.
- **Decision 5 — Safe shopper/assistant text rendering:** Use DOM node creation,
  `textContent`, CSS whitespace preservation, and event listeners only; add no
  Markdown/HTML renderer. **Reason:** Model and shopper text is untrusted.
  **Consequence:** tags, scripts, and Markdown appear literally and cannot create
  executable content or model-authored links.
- **Decision 6 — Recommendation-card authority mapping:** Create cards only from
  validated `recommendations` fields, map the exact availability enum, show a
  matched variant only when structured, and create View product links only from
  the structured URL after safe-protocol validation. That exact URL resolves
  through the catalogue-backed product presenter. **Reason:** The backend is the
  commerce authority and the response has no image/description fields.
  **Consequence:** the UI never parses or embellishes product facts from prose or
  fixtures, current links do not lead to local 404 pages, and no link claims a
  purchase action.
- **Decision 7 — Promotion/pricing presentation and association:** Present
  promotion status only from `promotion`; place `pricing` only on the unique card
  whose exact ID equals `pricing.product_id`; format values but never calculate a
  discount. **Reason:** Phase 7 exposes one quote and explicitly identifies its
  authoritative target. **Consequence:** valid codes without pricing remain
  unapplied status, negative codes have no quote, and unmatched pricing fails
  closed rather than being moved to the first card.
- **Decision 8 — Loading/error/retry behavior:** Use one in-flight guard, disable
  Send and New conversation, expose polite loading status, retain the submitted
  draft on failure, and require an explicit retry. Render only fixed safe error
  copy. **Reason:** This prevents duplicate local sends and avoids leaking
  provider/internal details; the API lacks idempotency for automatic retry.
  **Consequence:** ambiguous network failures are recoverable but not silently
  resent.
- **Decision 9 — Responsive/accessibility baseline:** Use semantic landmarks,
  labelled native controls, live regions, visible focus, adequate contrast and
  touch targets, reduced motion, keyboard support, and a 320px-to-desktop layout.
  **Reason:** These are necessary for a credible shopper demo, not optional
  polish. **Consequence:** accessibility and responsive behavior are manual
  acceptance gates alongside structural automated checks.
- **Decision 10 — Automated versus manual UI testing:** Automate FastAPI routes,
  assets, headers, API/OpenAPI regression, and narrow source trust-boundary
  checks with pytest; use a detailed manual browser matrix for DOM interaction,
  focus, storage, responsive, and accessibility behavior. **Reason:** The repo
  has no JavaScript/DOM/browser runner, and adding one solely for this small page
  is disproportionate. **Consequence:** CI remains Python-only; if an established
  lightweight frontend runner appears later, behavioral cases should migrate to
  it.
- **Decision 11 — OpenAPI/API regression protection:** Keep root/static routes
  out of OpenAPI and leave `/api/v1/chat`, `/api/v1/traces/{trace_id}`, models,
  status codes, and operation IDs unchanged. **Reason:** Phase 8 consumes the V1
  API and has no authority to reshape it. **Consequence:** existing contract
  tests remain applicable and the YAML file receives no edit.
- **Decision 12 — Secret/security boundaries:** Add a same-origin CSP/header
  baseline; call only `/api/v1/chat`; do not store trace IDs/raw responses; never
  include OpenAI keys, endpoints, hidden instructions, tool payloads, commerce
  rules, or unsafe dynamic HTML in assets. **Reason:** the browser is an untrusted
  presentation client, not an agent or commerce boundary. **Consequence:** all
  privileged work remains behind FastAPI and source-safety checks can catch
  accidental exposure.
- **Decision 13 — Live UI acceptance criteria:** Manually run the specified
  three-turn waterproof/blue/£120/WELCOME10 scenario when credentials are
  available and verify session reuse, structured card/link/status, exact pricing
  association, loading/error behavior, and absence of prose-derived commerce
  data. **Reason:** offline fakes cannot prove real provider and browser
  integration. **Consequence:** the check is potentially billable, never in CI,
  and is recorded as not run when credentials are unavailable.
- **Decision 14 — Stale-session behavior:** Accept the V1 limitation and submit a
  retained `sessionStorage` ID unchanged even when process-local backend state
  may have been lost. Add no expiry heuristic, hidden state probe, automatic ID
  replacement, or API field; explain the limitation and keep New conversation
  as the explicit reset. **Reason:** the current API deliberately accepts an
  unknown non-empty ID as a fresh state record and exposes no reliable freshness
  metadata. **Consequence:** after restart the backend may begin fresh state
  under the retained ID, and the UI neither detects nor conceals that behavior.
- **Decision 15 — Product URL destination boundary:** Add schema-hidden,
  read-only `GET /products/{slug}` presentation using the existing
  `CommerceService`. Resolve only one exact `Product.product_url` match, render
  escaped deterministic catalogue fields, and return 404 otherwise. **Reason:**
  recommendation cards must preserve their authoritative structured paths
  without shipping broken local links. **Consequence:** every current catalogue
  URL has a local non-404 destination, while no product API, new commerce-domain
  capability, model fact, cart, checkout, payment, or purchase mutation is added.
- **Decision 16 — Transcript storage:** Keep transcript DOM-only and do not store
  raw turn payloads in Web Storage. **Reason:** the requested continuity needs
  only the opaque session ID, and reconstructing turns adds privacy/state
  complexity without backend synchronization. **Consequence:** reload shows an
  empty visual log with an accurate continuity notice while backend context can
  continue.

## Risks and follow-ups

- **Product-page presentation can drift:** The route must enumerate through the
  existing commerce service and match `Product.product_url` exactly. Keep its
  renderer typed and focused on `Product` fields so a future catalogue-model
  change cannot silently introduce model prose, a fixture read, or duplicate
  commerce logic.
- **Duplicate authoritative product URLs:** URL uniqueness is not currently a
  domain invariant. The current fixture is unique; the presentation resolver
  must fail closed when a path has anything other than one match. A future
  domain-level uniqueness rule requires separate justification.
- **Stale session cannot be detected:** This is an accepted V1 limitation. The
  unchanged contract provides no session existence, generation, or reset marker;
  an unknown retained ID becomes a fresh backend session. Do not add expiry or
  probing. Documentation and explicit New conversation reset are the truthful
  treatment.
- **Visual transcript/backend context divergence:** Reload clears DOM bubbles but
  retains the ID; restart may clear backend context but leave current DOM bubbles.
  The continuity note must be precise. Durable synchronized conversation history
  requires a separately designed API and persistence layer.
- **Network retry ambiguity:** Without an idempotency key, a failed connection may
  hide a completed backend turn. Avoid auto-retry and explain the choice; a future
  contract could add client turn IDs if evaluation shows a need.
- **No automated DOM runner:** Source assertions cannot prove event behavior,
  focus, announcements, or responsive layout. The manual checklist is therefore
  part of Definition of Done, not optional polish.
- **Package asset inclusion:** Non-Python files must exist in built artifacts.
  Verify rather than assume uv's defaults, and keep any packaging configuration
  narrow.
- **Browser storage may be disabled:** Catch storage exceptions and continue
  in-memory. This loses continuity on reload but must not break current-page chat.
- **Malformed successful response after server commit:** The UI may reject data
  even though the backend advanced state. Preserve the draft, do not auto-retry,
  and surface a generic unexpected-response state. Fix any reproducible backend
  contract violation at its source.
- **Unsupported prose claims remain possible:** Structured cards/pricing are
  authoritative, but free-form assistant prose is not independently verified.
  Render it only as conversation and rely on the existing agent/evaluation
  boundaries; do not parse or rewrite it in Phase 8.
- **Product URL policy may evolve:** Current backend domain validation permits
  relative `/products/...` URLs while the public YAML declares a string. Safe
  http/https resolution and the local exact-path presenter are presentation
  behavior, not a commerce override. Reconcile deliberately if the contract
  later adopts another scheme or an external storefront.
- **Accessibility varies by browser/assistive technology:** Test at least one
  Chromium-family browser and, where available, Firefox plus a screen-reader
  smoke. A full audited design system remains outside V1.
- **CSP and docs routes:** The root document's CSP applies to the UI document,
  not FastAPI's separately served `/docs` HTML. Do not install a global policy
  that accidentally breaks existing OpenAPI documentation.
- **Multi-worker behavior remains unsupported:** A browser can be routed to a
  worker that lacks its process-local session. Production affinity/shared state
  is explicitly deferred and must not be hidden by frontend logic.
- **Future frontend growth:** If the UI later gains routing, many screens, or
  complex interaction, reassess the no-build approach in a separate plan. Do
  not pre-emptively add framework infrastructure to Phase 8.

## Outcome

Phase 8 is not implemented yet. This document is the planning-only deliverable
created on 2026-09-07. No source, test, contract, fixture, dependency, workflow,
or README behavior was changed.

When implementation completes, replace this section with:

- the actual files and shopper-visible behavior delivered;
- route/static/package decisions and any deviations from this plan;
- automated command results and browser/viewports manually checked;
- the live OpenAI-backed acceptance result or explicit credential-based deferral;
- confirmation that the public YAML/OpenAPI chat and trace contracts remained
  unchanged;
- remaining limitations, especially process-local sessions and the read-only,
  non-purchasing product-page boundary.
