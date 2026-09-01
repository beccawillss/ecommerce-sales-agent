"""Deterministic validation and hydration for untrusted product nominations."""

import re
import unicodedata
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from salesagent.domain.models import Product
from salesagent.services.commerce import CommerceService

Availability = Literal["in_stock", "out_of_stock", "partial", "unknown"]
MAX_RECOMMENDATIONS = 3
MAX_REJECTED_ID_DISPLAY = 64


@dataclass(frozen=True, slots=True)
class HydratedRecommendation:
    """Customer-facing product facts copied from current commerce data."""

    product_id: str
    name: str
    price: Decimal
    currency: Literal["GBP"]
    product_url: str
    availability: Availability


@dataclass(frozen=True, slots=True)
class RecommendationHydrationResult:
    """Accepted cards and safe evidence for every rejected nomination."""

    recommendations: tuple[HydratedRecommendation, ...]
    accepted_product_ids: tuple[str, ...]
    all_products_exist: bool
    prices_match_catalogue: bool
    urls_match_catalogue: bool
    stock_claims_validated: bool
    validation_errors: tuple[str, ...]


class RecommendationHydrator:
    """Re-fetch, validate, and hydrate model-nominated product IDs."""

    def __init__(self, commerce_service: CommerceService) -> None:
        self._commerce = commerce_service

    def hydrate(
        self,
        nominated_product_ids: Iterable[str],
        grounded_product_ids: Collection[str],
    ) -> RecommendationHydrationResult:
        """Return only existing, current-turn-grounded authoritative cards."""
        nominations = tuple(nominated_product_ids)
        if len(nominations) > MAX_RECOMMENDATIONS:
            raise ValueError("at most three product nominations are allowed")

        grounded_keys = {
            product_id.strip().casefold()
            for product_id in grounded_product_ids
            if product_id.strip()
        }
        seen: set[str] = set()
        recommendations: list[HydratedRecommendation] = []
        errors: list[str] = []
        all_products_exist = True

        for nominated_id in nominations:
            cleaned_id = nominated_id.strip()
            normalized_id = cleaned_id.casefold()
            if normalized_id in seen:
                errors.append(f"duplicate_product_id:{_display_product_id(cleaned_id)}")
                continue
            seen.add(normalized_id)

            try:
                product = self._commerce.get_product(cleaned_id)
            except Exception:
                all_products_exist = False
                errors.append(
                    f"product_lookup_failed:{_display_product_id(cleaned_id)}"
                )
                continue

            if product is None:
                all_products_exist = False
                errors.append(f"unknown_product_id:{_display_product_id(cleaned_id)}")
                continue
            if product.id.casefold() not in grounded_keys:
                errors.append(
                    f"ungrounded_product_id:{_display_product_id(product.id)}"
                )
                continue

            recommendations.append(_hydrate_product(product))

        accepted_ids = tuple(item.product_id for item in recommendations)
        return RecommendationHydrationResult(
            recommendations=tuple(recommendations),
            accepted_product_ids=accepted_ids,
            all_products_exist=all_products_exist,
            prices_match_catalogue=True,
            urls_match_catalogue=True,
            stock_claims_validated=True,
            validation_errors=tuple(errors),
        )


def _hydrate_product(product: Product) -> HydratedRecommendation:
    return HydratedRecommendation(
        product_id=product.id,
        name=product.name,
        price=product.price,
        currency=product.currency,
        product_url=product.product_url,
        availability=_availability(product),
    )


def _availability(product: Product) -> Availability:
    stocks = tuple(variant.stock for variant in product.variants)
    if not stocks:
        return "unknown"
    if all(stock > 0 for stock in stocks):
        return "in_stock"
    if all(stock == 0 for stock in stocks):
        return "out_of_stock"
    return "partial"


def _display_product_id(product_id: str) -> str:
    stripped = product_id.strip()
    visible = "".join(
        "�" if unicodedata.category(character).startswith("C") else character
        for character in stripped
    )
    collapsed = re.sub(r"\s+", " ", visible)
    if len(collapsed) <= MAX_REJECTED_ID_DISPLAY:
        return collapsed
    return f"{collapsed[: MAX_REJECTED_ID_DISPLAY - 1]}…"
