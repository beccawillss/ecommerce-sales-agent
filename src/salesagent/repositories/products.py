"""Validated JSON-backed product catalogue repository."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from salesagent.domain.models import Product, ProductSearchCriteria


class ProductDataError(ValueError):
    """Raised when the product catalogue cannot be loaded safely."""


class _ProductDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    products: tuple[Product, ...]

    @model_validator(mode="after")
    def product_ids_are_unique(self) -> "_ProductDocument":
        keys = {product.id.casefold() for product in self.products}
        if len(keys) != len(self.products):
            raise ValueError("product IDs must be unique")
        return self


class ProductRepository:
    """Load, retrieve, and deterministically filter catalogue products."""

    def __init__(self, path: Path) -> None:
        products = self._load(path)
        self._products = tuple(
            sorted(products, key=lambda product: product.id.casefold())
        )
        self._products_by_id = {
            product.id.casefold(): product for product in self._products
        }

    @staticmethod
    def _load(path: Path) -> tuple[Product, ...]:
        try:
            document = _ProductDocument.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValidationError) as error:
            raise ProductDataError(
                f"unable to load product data from {path}"
            ) from error
        return document.products

    def get(self, product_id: str) -> Product | None:
        """Return a product by stable ID, or ``None`` when it is unknown."""
        return self._products_by_id.get(product_id.strip().casefold())

    def all(self) -> tuple[Product, ...]:
        """Return the complete catalogue in product-ID order."""
        return self._products

    def search(self, criteria: ProductSearchCriteria) -> tuple[Product, ...]:
        """Apply all criteria and order matching products by price, then ID."""
        matches = [
            product for product in self._products if self._matches(product, criteria)
        ]
        return tuple(sorted(matches, key=lambda product: (product.price, product.id)))

    @classmethod
    def _matches(cls, product: Product, criteria: ProductSearchCriteria) -> bool:
        if criteria.category and not cls._same(product.category, criteria.category):
            return False
        if criteria.activity and not cls._contains(
            product.activities, criteria.activity
        ):
            return False
        if not cls._contains_all(product.weather, criteria.weather):
            return False
        if not cls._contains_all(product.features, criteria.features):
            return False
        if (
            criteria.maximum_price is not None
            and product.price > criteria.maximum_price
        ):
            return False
        return cls._matches_inventory_filters(product, criteria)

    @classmethod
    def _matches_inventory_filters(
        cls, product: Product, criteria: ProductSearchCriteria
    ) -> bool:
        if criteria.colour is None and criteria.size is None:
            return not criteria.in_stock_only or product.total_stock > 0

        variants = (
            variant
            for variant in product.variants
            if (criteria.colour is None or cls._same(variant.colour, criteria.colour))
            and (criteria.size is None or cls._same(variant.size, criteria.size))
        )
        if criteria.in_stock_only:
            return any(variant.stock > 0 for variant in variants)
        return any(True for _ in variants)

    @staticmethod
    def _same(left: str, right: str) -> bool:
        return left.strip().casefold() == right.strip().casefold()

    @classmethod
    def _contains(cls, values: tuple[str, ...], required: str) -> bool:
        return any(cls._same(value, required) for value in values)

    @classmethod
    def _contains_all(cls, values: tuple[str, ...], required: tuple[str, ...]) -> bool:
        return all(cls._contains(values, item) for item in required)
