"""Offline route, asset, and trust-boundary tests for the shopper web UI."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from salesagent.api.routes.ui import _find_product_by_url, _render_product_page
from salesagent.config import Settings
from salesagent.main import create_app
from salesagent.repositories.products import ProductRepository
from tests.fakes import ScriptedResponsesClient

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ProductRepository(ROOT / "data" / "products.json")


@pytest.fixture
def client() -> Iterator[TestClient]:
    application = create_app(
        Settings(enable_eval_traces=True),
        responses_client=ScriptedResponsesClient([]),
    )
    with TestClient(application) as test_client:
        yield test_client


def test_root_serves_semantic_shopper_shell_with_security_headers(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    policy = response.headers["content-security-policy"]
    assert "default-src 'self'" in policy
    assert "script-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert '<html lang="en">' in response.text
    assert 'name="viewport"' in response.text
    assert '<main id="main-content"' in response.text
    assert '<form id="chat-form"' in response.text
    assert '<label for="message-input">' in response.text
    assert 'id="new-conversation"' in response.text
    assert 'id="request-status"' in response.text
    assert 'id="request-error"' in response.text
    assert 'role="log"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'role="alert"' in response.text
    assert 'aria-busy="false"' in response.text
    assert 'maxlength="4000"' in response.text
    assert "choose New conversation if the context appears lost" in response.text
    assert "<noscript>" in response.text
    assert 'href="/static/app.css"' in response.text
    assert 'src="/static/app.js"' in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/app.css", "text/css"),
        ("/static/app.js", "text/javascript"),
    ],
)
def test_static_assets_are_served_with_expected_media_types(
    client: TestClient,
    path: str,
    content_type: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.text.strip()


def test_unknown_static_asset_returns_not_found(client: TestClient) -> None:
    response = client.get("/static/not-present.js")

    assert response.status_code == 404
    assert "<!doctype html>" not in response.text.casefold()


def test_every_authoritative_product_url_resolves_to_catalogue_page(
    client: TestClient,
) -> None:
    for product in PRODUCTS.all():
        response = client.get(product.product_url, follow_redirects=False)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert product.name in response.text
        assert f"£{product.price:.2f}" in response.text
        assert product.currency in response.text
        assert f'href="{product.product_url}"' in response.text
        for variant in product.variants:
            assert variant.colour in response.text
            assert variant.size in response.text
            assert f"<td>{variant.stock}</td>" in response.text
        lowered = response.text.casefold()
        assert "openai" not in lowered
        assert "/api/v1/" not in lowered
        assert "<form" not in lowered


@pytest.mark.parametrize(
    "path",
    [
        "/products/not-a-product",
        "/products/Apex-Alpine",
        "/products/apex-alpine/extra",
    ],
)
def test_unknown_or_noncanonical_product_paths_return_not_found(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404


def test_product_url_resolver_requires_one_exact_match() -> None:
    product = PRODUCTS.all()[0]

    assert _find_product_by_url((product,), product.product_url) is product
    assert _find_product_by_url((product,), product.product_url.upper()) is None
    assert _find_product_by_url((product, product), product.product_url) is None


def test_product_page_escapes_catalogue_text_and_has_no_mutation_surface() -> None:
    product = PRODUCTS.all()[0].model_copy(
        update={
            "name": '<script src="//attacker.test/x.js">unsafe</script>',
            "features": ('<button formaction="/pay">Pay</button>',),
        }
    )

    document = _render_product_page(product)

    assert '<script src="//attacker.test/x.js">' not in document
    assert "&lt;script src=&quot;//attacker.test/x.js&quot;&gt;" in document
    assert '<button formaction="/pay">' not in document
    assert "&lt;button formaction=&quot;/pay&quot;&gt;" in document
    assert "<form" not in document.casefold()
    assert "/api/v1/" not in document


def test_ui_routes_do_not_change_generated_openapi(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()

    assert set(openapi["paths"]) == {
        "/health",
        "/api/v1/chat",
        "/api/v1/traces/{trace_id}",
    }
    assert openapi["paths"]["/api/v1/chat"]["post"]["operationId"] == "chat"
    assert (
        openapi["paths"]["/api/v1/traces/{trace_id}"]["get"]["operationId"]
        == "getTrace"
    )


def test_frontend_assets_contain_no_secret_provider_or_trace_surface(
    client: TestClient,
) -> None:
    html = client.get("/").text
    javascript = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text
    combined = f"{html}\n{javascript}\n{stylesheet}"

    for forbidden in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_REASONING_EFFORT",
        "api.openai.com",
        "previous_response_id",
    ):
        assert forbidden not in combined
    assert "/api/v1/traces" not in combined
    assert '"/health"' not in javascript
    assert "localStorage" not in javascript
    assert "innerHTML" not in javascript
    assert "insertAdjacentHTML" not in javascript
    assert "document.write" not in javascript
    assert "eval(" not in javascript
    assert "JKT-" not in javascript
    assert "WELCOME10" not in javascript


def test_chat_script_uses_existing_api_and_tab_scoped_session_state(
    client: TestClient,
) -> None:
    javascript = client.get("/static/app.js").text

    assert 'const CHAT_ENDPOINT = "/api/v1/chat"' in javascript
    assert 'method: "POST"' in javascript
    assert "window.sessionStorage.getItem" in javascript
    assert "window.sessionStorage.setItem" in javascript
    assert "window.sessionStorage.removeItem" in javascript
    assert "payload.session_id = expectedSessionId" in javascript
    assert "requestInFlight" in javascript
    assert "chatForm.requestSubmit()" in javascript
    assert "!event.shiftKey" in javascript
    assert "messages.replaceChildren(welcome)" in javascript
    assert "response.text(" not in javascript


def test_chat_script_renders_only_structured_recommendation_fields(
    client: TestClient,
) -> None:
    javascript = client.get("/static/app.js").text

    assert "name.textContent = recommendation.name" in javascript
    assert "recommendation.price" in javascript
    assert "recommendation.currency" in javascript
    assert "recommendation.matched_variant.colour" in javascript
    assert "recommendation.matched_variant.size" in javascript
    assert "recommendation.matched_variant.stock" in javascript
    assert "productLink.href = recommendation.product_url" in javascript
    assert 'productLink.target = "_blank"' in javascript
    assert 'productLink.rel = "noopener noreferrer"' in javascript
    assert "new URL(value.product_url, window.location.origin)" in javascript
    assert '["http:", "https:"]' in javascript


def test_chat_script_maps_all_availability_and_exact_pricing_target(
    client: TestClient,
) -> None:
    javascript = client.get("/static/app.js").text

    assert 'in_stock: "In stock"' in javascript
    assert 'partial: "Some variants available"' in javascript
    assert 'out_of_stock: "Out of stock"' in javascript
    assert 'unknown: "Availability not confirmed"' in javascript
    assert "new Map()" in javascript
    assert "cardsByProductId.set(recommendation.product_id, card)" in javascript
    assert "cardsByProductId.get(response.pricing.product_id)" in javascript
    assert "formatMoney(pricing.base_price, pricing.currency)" in javascript
    assert "formatMoney(pricing.final_price, pricing.currency)" in javascript
    assert 'new Intl.NumberFormat("en-GB"' in javascript


def test_chat_script_fails_closed_on_ambiguous_or_incompatible_quotes(
    client: TestClient,
) -> None:
    javascript = client.get("/static/app.js").text

    assert "recommendationIds.size !== recommendations.length" in javascript
    assert "!recommendationIds.has(pricing.product_id)" in javascript
    assert "promotion === null" in javascript
    assert "!promotion.valid" in javascript
    assert "pricing.discount_code !== promotion.code" in javascript
    assert "Number.isFinite(value)" in javascript
    assert "Number.isInteger(value.stock)" in javascript


def test_frontend_has_accessible_failure_and_responsive_state_hooks(
    client: TestClient,
) -> None:
    javascript = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text

    assert 'messages.setAttribute("aria-busy", String(isBusy))' in javascript
    assert '"You — message not answered"' in javascript
    assert 'showError("Enter a message before sending.")' in javascript
    assert "error.status === 500" in javascript
    assert 'error.kind === "response"' in javascript
    assert "response.message.trim()" in javascript
    assert ":focus-visible" in stylesheet
    assert "@media (max-width: 700px)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ".recommendation-out_of_stock .product-link" in stylesheet
