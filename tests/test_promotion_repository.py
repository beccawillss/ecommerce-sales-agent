"""Tests for validated promotion data loading."""

from decimal import Decimal
from pathlib import Path

import pytest

from salesagent.repositories.promotions import PromotionDataError, PromotionRepository

ROOT = Path(__file__).resolve().parents[1]
DISCOUNTS_PATH = ROOT / "data" / "discounts.json"


def test_promotions_load_and_lookup_is_case_insensitive() -> None:
    repository = PromotionRepository(DISCOUNTS_PATH)

    welcome = repository.get("welcome10")

    assert welcome is not None
    assert welcome.code == "WELCOME10"
    assert welcome.discount_percent == Decimal("10")
    assert welcome.active is True

    summer = repository.get("SUMMER20")
    assert summer is not None
    assert summer.discount_percent == Decimal("20")
    assert summer.active is False
    assert repository.get("STAFF99") is None


def test_duplicate_promotion_codes_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-promotions.json"
    path.write_text(
        """{
            "promotions": [
                {"code": "WELCOME10", "discount_percent": "10", "active": true},
                {"code": "welcome10", "discount_percent": "5", "active": true}
            ]
        }""",
        encoding="utf-8",
    )

    with pytest.raises(PromotionDataError, match="unable to load promotion data"):
        PromotionRepository(path)


@pytest.mark.parametrize(
    "content",
    [
        "not valid JSON",
        '{"promotions": [{"code": "BROKEN", "active": true}]}',
    ],
)
def test_malformed_promotion_data_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "malformed-promotions.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(PromotionDataError, match="unable to load promotion data"):
        PromotionRepository(path)
