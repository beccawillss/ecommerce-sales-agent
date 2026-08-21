"""Tests for validated product data loading and retrieval."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from salesagent.repositories.products import ProductDataError, ProductRepository

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = ROOT / "data" / "products.json"


def test_valid_catalogue_loads_anchor_products_with_decimal_prices() -> None:
    repository = ProductRepository(PRODUCTS_PATH)
    anchor_prices = {
        "JKT-001": Decimal("145.00"),
        "JKT-002": Decimal("75.00"),
        "JKT-003": Decimal("110.00"),
        "JKT-004": Decimal("195.00"),
        "JKT-005": Decimal("85.00"),
        "INS-001": Decimal("130.00"),
        "SOCK-001": Decimal("18.00"),
    }

    assert len(repository.all()) == 17
    for product_id, expected_price in anchor_prices.items():
        product = repository.get(product_id)
        assert product is not None
        assert product.price == expected_price
        assert isinstance(product.price, Decimal)

    apex = repository.get("JKT-001")
    assert apex is not None
    assert apex.product_url == "/products/apex-alpine"

    socks = repository.get("SOCK-001")
    assert socks is not None
    assert socks.waterproof_rating == "none"
    assert {"heated", "electronic", "waterproof"}.isdisjoint(socks.features)


def test_known_and_unknown_product_retrieval_is_explicit() -> None:
    repository = ProductRepository(PRODUCTS_PATH)

    product = repository.get("jkt-003")

    assert product is not None
    assert product.name == "Ridgeway Rain Shell"
    assert repository.get("UNKNOWN-001") is None


def test_duplicate_product_ids_are_rejected(tmp_path: Path) -> None:
    document: dict[str, Any] = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    document["products"].append(document["products"][0])
    path = tmp_path / "duplicate-products.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ProductDataError, match="unable to load product data"):
        ProductRepository(path)


@pytest.mark.parametrize(
    "content",
    [
        "not valid JSON",
        '{"products": [{"id": "BROKEN"}]}',
    ],
)
def test_malformed_product_data_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "malformed-products.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ProductDataError, match="unable to load product data"):
        ProductRepository(path)
