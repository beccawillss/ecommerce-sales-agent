"""JSON-backed repositories for authoritative commerce data."""

from salesagent.repositories.products import ProductDataError, ProductRepository
from salesagent.repositories.promotions import PromotionDataError, PromotionRepository
from salesagent.repositories.traces import InMemoryTraceRepository

__all__ = [
    "ProductDataError",
    "ProductRepository",
    "PromotionDataError",
    "PromotionRepository",
    "InMemoryTraceRepository",
]
