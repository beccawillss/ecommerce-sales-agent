"""Behavior and safety tests for the deterministic tool dispatcher."""

import json
from pathlib import Path
from typing import Any

import pytest

from salesagent.agent.tools.dispatcher import ToolDispatcher
from salesagent.agent.tools.models import ToolExecutionResult
from salesagent.domain.models import Product
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.services.commerce import CommerceService

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = ROOT / "data" / "products.json"
DISCOUNTS_PATH = ROOT / "data" / "discounts.json"


class FailingCommerceService(CommerceService):
    """Test double that simulates an unexpected commerce-layer failure."""

    def get_product(self, product_id: str) -> Product | None:
        raise RuntimeError(f"sensitive repository detail for {product_id}")


@pytest.fixture
def dispatcher() -> ToolDispatcher:
    commerce = CommerceService(
        products=ProductRepository(PRODUCTS_PATH),
        promotions=PromotionRepository(DISCOUNTS_PATH),
    )
    return ToolDispatcher(commerce)


def successful_data(result: ToolExecutionResult) -> dict[str, Any]:
    assert result.success is True
    assert result.error is None
    assert result.data is not None
    return result.data


@pytest.mark.parametrize(
    ("arguments", "expected_product_id"),
    [
        (
            {
                "category": "jacket",
                "activity": "hiking",
                "weather": ["heavy-rain"],
                "maximum_price": "160.00",
            },
            "JKT-001",
        ),
        (
            {
                "category": "jacket",
                "activity": "hiking",
                "weather": ["moderate-rain"],
                "maximum_price": "120.00",
            },
            "JKT-003",
        ),
        (
            {
                "activity": "cycling",
                "features": ["lightweight"],
                "in_stock_only": True,
            },
            "JKT-005",
        ),
    ],
)
def test_search_products_returns_expected_authoritative_candidates(
    dispatcher: ToolDispatcher,
    arguments: dict[str, object],
    expected_product_id: str,
) -> None:
    result = dispatcher.dispatch("search_products", arguments)
    products = successful_data(result)["products"]

    assert expected_product_id in [product["product_id"] for product in products]


def test_search_products_empty_result_is_successful(
    dispatcher: ToolDispatcher,
) -> None:
    result = dispatcher.dispatch(
        "search_products",
        {"category": "socks", "features": ["waterproof", "electronic"]},
    )
    data = successful_data(result)

    assert data == {"products": [], "count": 0}


def test_search_products_preserves_phase_one_order(dispatcher: ToolDispatcher) -> None:
    result = dispatcher.dispatch(
        "search_products",
        {"activity": "cycling", "features": ["lightweight"]},
    )
    products = successful_data(result)["products"]

    assert [product["product_id"] for product in products] == ["JKT-002", "JKT-005"]


def test_get_product_returns_explicit_authoritative_facts(
    dispatcher: ToolDispatcher,
) -> None:
    result = dispatcher.dispatch("get_product", {"product_id": "JKT-001"})
    data = successful_data(result)

    assert data["product_id"] == "JKT-001"
    assert data["name"] == "Apex Alpine Waterproof Jacket"
    assert data["price"] == "145.00"
    assert data["currency"] == "GBP"
    assert data["product_url"] == "/products/apex-alpine"
    assert data["total_stock"] == 4


def test_unknown_product_is_a_predictable_tool_failure(
    dispatcher: ToolDispatcher,
) -> None:
    result = dispatcher.dispatch("get_product", {"product_id": "UNKNOWN-001"})

    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "product_not_found"


@pytest.mark.parametrize(
    ("product_id", "colour", "size", "stock", "available", "status"),
    [
        ("JKT-001", "Ocean Blue", "M", 4, True, "in_stock"),
        ("JKT-001", "Black", "M", 0, False, "out_of_stock"),
        ("JKT-001", "Ocean Blue", "XL", None, False, "variant_not_found"),
        ("UNKNOWN-001", "Black", "M", None, False, "product_not_found"),
    ],
)
def test_check_inventory_preserves_exact_domain_outcomes(
    dispatcher: ToolDispatcher,
    product_id: str,
    colour: str,
    size: str,
    stock: int | None,
    available: bool,
    status: str,
) -> None:
    result = dispatcher.dispatch(
        "check_inventory",
        {"product_id": product_id, "colour": colour, "size": size},
    )
    data = successful_data(result)

    assert data["stock"] == stock
    assert data["available"] is available
    assert data["status"] == status


@pytest.mark.parametrize(
    ("code", "valid", "discount_percent", "reason"),
    [
        ("WELCOME10", True, "10", "active"),
        ("SUMMER20", False, None, "inactive"),
        ("STAFF99", False, None, "unknown_code"),
        ("SECRET75", False, None, "unknown_code"),
        ("RANDOM42", False, None, "unknown_code"),
    ],
)
def test_validate_discount_preserves_domain_outcomes(
    dispatcher: ToolDispatcher,
    code: str,
    valid: bool,
    discount_percent: str | None,
    reason: str,
) -> None:
    result = dispatcher.dispatch("validate_discount", {"code": code})
    data = successful_data(result)

    assert data["valid"] is valid
    assert data["discount_percent"] == discount_percent
    assert data["reason"] == reason


def test_unknown_tool_fails_without_executing_anything(
    dispatcher: ToolDispatcher,
) -> None:
    result = dispatcher.dispatch("delete_inventory", {})

    assert result.success is False
    assert result.arguments is None
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "unknown_tool"


def test_execution_failure_is_safe_and_does_not_expose_exception_text() -> None:
    commerce = FailingCommerceService(
        products=ProductRepository(PRODUCTS_PATH),
        promotions=PromotionRepository(DISCOUNTS_PATH),
    )
    dispatcher = ToolDispatcher(commerce)

    result = dispatcher.dispatch("get_product", {"product_id": "JKT-001"})
    serialized = json.dumps(result.model_dump(mode="json"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "execution_error"
    assert "sensitive repository detail" not in serialized


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("get_product", {}),
        ("get_product", {"product_id": "JKT-001", "colour": "Black"}),
        ("check_inventory", {"product_id": "JKT-001", "size": "M"}),
        ("validate_discount", {"code": "WELCOME10", "active": True}),
        ("search_products", {"maximum_price": {"amount": "160.00"}}),
        ("search_products", {"unknown_filter": "value"}),
    ],
)
def test_invalid_arguments_fail_before_commerce_execution(
    dispatcher: ToolDispatcher,
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    result = dispatcher.dispatch(tool_name, arguments)

    assert result.success is False
    assert result.arguments is None
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "invalid_arguments"


def test_dispatcher_never_executes_callable_arguments(
    dispatcher: ToolDispatcher,
) -> None:
    called = False

    def dangerous() -> None:
        nonlocal called
        called = True

    result = dispatcher.dispatch(
        "get_product",
        {"product_id": "JKT-001", "callback": dangerous},
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_arguments"
    assert called is False


def test_all_result_envelopes_are_standard_json_serializable(
    dispatcher: ToolDispatcher,
) -> None:
    results = [
        dispatcher.dispatch("search_products", {"maximum_price": "20.00"}),
        dispatcher.dispatch("get_product", {"product_id": "JKT-001"}),
        dispatcher.dispatch(
            "check_inventory",
            {"product_id": "JKT-001", "colour": "Ocean Blue", "size": "M"},
        ),
        dispatcher.dispatch("validate_discount", {"code": "WELCOME10"}),
        dispatcher.dispatch("get_product", {}),
        dispatcher.dispatch("not_a_tool", {}),
    ]

    for result in results:
        json.dumps(result.model_dump(mode="json"))


def test_tool_calls_do_not_mutate_authoritative_fixture_files(
    dispatcher: ToolDispatcher,
) -> None:
    products_before = PRODUCTS_PATH.read_bytes()
    discounts_before = DISCOUNTS_PATH.read_bytes()

    dispatcher.dispatch("search_products", {})
    dispatcher.dispatch("get_product", {"product_id": "JKT-001"})
    dispatcher.dispatch(
        "check_inventory",
        {"product_id": "JKT-001", "colour": "Ocean Blue", "size": "M"},
    )
    dispatcher.dispatch("validate_discount", {"code": "WELCOME10"})

    assert PRODUCTS_PATH.read_bytes() == products_before
    assert DISCOUNTS_PATH.read_bytes() == discounts_before
