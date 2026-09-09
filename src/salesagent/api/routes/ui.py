"""Shopper-facing HTML routes backed by the existing commerce service."""

from collections.abc import Iterable
from html import escape
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse

from salesagent.domain.models import Product, ProductSearchCriteria
from salesagent.services.commerce import CommerceService

HTML_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def create_ui_router(
    commerce_service: CommerceService,
    *,
    index_path: Path,
) -> APIRouter:
    """Create human-facing routes without widening the public API schema."""
    router = APIRouter(include_in_schema=False)

    @router.get("/", response_class=FileResponse)
    def shopper_ui() -> FileResponse:
        """Return the static shopper application shell."""
        return FileResponse(
            index_path,
            media_type="text/html",
            headers=HTML_SECURITY_HEADERS,
        )

    @router.get("/products/{slug}", response_class=HTMLResponse)
    def product_page(slug: str) -> HTMLResponse:
        """Render one existing product at its authoritative catalogue URL."""
        requested_path = f"/products/{slug}"
        product = _find_product_by_url(
            commerce_service.search_products(ProductSearchCriteria()),
            requested_path,
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )
        return HTMLResponse(
            _render_product_page(product),
            headers=HTML_SECURITY_HEADERS,
        )

    return router


def _find_product_by_url(
    products: Iterable[Product],
    requested_path: str,
) -> Product | None:
    """Return the sole exact authoritative URL match, failing closed otherwise."""
    matches = tuple(
        product for product in products if product.product_url == requested_path
    )
    return matches[0] if len(matches) == 1 else None


def _render_product_page(product: Product) -> str:
    """Build a small escaped catalogue page from one authoritative product."""
    name = escape(product.name)
    category = escape(product.category.replace("-", " ").title())
    price = escape(f"£{product.price:.2f}")
    currency = escape(product.currency)
    product_url = escape(product.product_url, quote=True)
    activities = _render_tags(product.activities)
    weather = _render_tags(product.weather)
    features = _render_tags(product.features)
    seasons = _render_tags(product.season)
    waterproof_rating = escape(product.waterproof_rating.replace("-", " ").title())
    warmth = escape(product.warmth.replace("-", " ").title())
    variants = "".join(
        "<tr>"
        f"<td>{escape(variant.colour)}</td>"
        f"<td>{escape(variant.size)}</td>"
        f"<td>{variant.stock}</td>"
        "</tr>"
        for variant in product.variants
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Catalogue details for {name}">
  <link rel="canonical" href="{product_url}">
  <link rel="stylesheet" href="/static/app.css">
  <title>{name} · Sales Agent</title>
</head>
<body class="product-document">
  <a class="skip-link" href="#product-details">Skip to product details</a>
  <header class="site-header compact-header">
    <a class="brand" href="/" aria-label="Sales Agent home">
      <span class="brand-mark" aria-hidden="true">SA</span>
      <span><strong>Sales Agent</strong><small>Outdoor concierge</small></span>
    </a>
  </header>
  <main id="product-details" class="product-page">
    <a class="back-link" href="/">← Back to the concierge</a>
    <article class="product-detail-card">
      <p class="eyebrow">{category}</p>
      <h1>{name}</h1>
      <p class="product-detail-price">{price} <span>{currency}</span></p>
      <div class="product-fact-grid">
        <section><h2>Activities</h2><ul class="tag-list">{activities}</ul></section>
        <section><h2>Conditions</h2><ul class="tag-list">{weather}</ul></section>
        <section><h2>Features</h2><ul class="tag-list">{features}</ul></section>
        <section><h2>Seasons</h2><ul class="tag-list">{seasons}</ul></section>
      </div>
      <dl class="product-specs">
        <div><dt>Waterproof rating</dt><dd>{waterproof_rating}</dd></div>
        <div><dt>Warmth</dt><dd>{warmth}</dd></div>
      </dl>
      <section class="variants-section" aria-labelledby="variants-heading">
        <h2 id="variants-heading">Available variants</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th scope="col">Colour</th><th scope="col">Size</th><th scope="col">Stock</th></tr></thead>
            <tbody>{variants}</tbody>
          </table>
        </div>
      </section>
      <p class="product-page-note">Catalogue information only. Sales Agent does not place orders.</p>
    </article>
  </main>
</body>
</html>
"""


def _render_tags(values: Iterable[str]) -> str:
    return "".join(f"<li>{escape(value.replace('-', ' '))}</li>" for value in values)
