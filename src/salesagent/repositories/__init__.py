"""JSON-backed repositories for authoritative commerce data."""

from salesagent.repositories.products import ProductDataError, ProductRepository
from salesagent.repositories.promotions import PromotionDataError, PromotionRepository

__all__ = [
    "ProductDataError",
    "ProductRepository",
    "PromotionDataError",
    "PromotionRepository",
]
