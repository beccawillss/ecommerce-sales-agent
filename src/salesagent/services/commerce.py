"""Deterministic commerce capabilities backed by authoritative repositories."""

from salesagent.domain.models import (
    DiscountValidationResult,
    InventoryResult,
    Product,
    ProductSearchCriteria,
)
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository


class CommerceService:
    """Expose read-only catalogue, inventory, and promotion operations."""

    def __init__(
        self,
        products: ProductRepository,
        promotions: PromotionRepository,
    ) -> None:
        self._products = products
        self._promotions = promotions

    def search_products(self, criteria: ProductSearchCriteria) -> tuple[Product, ...]:
        """Return products satisfying every supplied deterministic constraint."""
        return self._products.search(criteria)

    def get_product(self, product_id: str) -> Product | None:
        """Return an authoritative product or ``None`` for an unknown ID."""
        return self._products.get(product_id)

    def check_inventory(
        self, product_id: str, colour: str, size: str
    ) -> InventoryResult:
        """Return stock for exactly the requested product variant."""
        requested_product_id = product_id.strip()
        requested_colour = colour.strip()
        requested_size = size.strip()
        product = self._products.get(requested_product_id)

        if product is None:
            return InventoryResult(
                product_id=requested_product_id,
                colour=requested_colour,
                size=requested_size,
                available=False,
                status="product_not_found",
            )

        variant = next(
            (
                item
                for item in product.variants
                if self._same(item.colour, requested_colour)
                and self._same(item.size, requested_size)
            ),
            None,
        )
        if variant is None:
            return InventoryResult(
                product_id=product.id,
                colour=requested_colour,
                size=requested_size,
                available=False,
                status="variant_not_found",
            )

        available = variant.stock > 0
        return InventoryResult(
            product_id=product.id,
            colour=requested_colour,
            size=requested_size,
            stock=variant.stock,
            available=available,
            status="in_stock" if available else "out_of_stock",
        )

    def validate_discount(self, code: str) -> DiscountValidationResult:
        """Validate a promotion without special-casing unknown codes."""
        canonical_code = code.strip().upper()
        promotion = self._promotions.get(canonical_code)
        if promotion is None:
            return DiscountValidationResult(
                code=canonical_code,
                valid=False,
                reason="unknown_code",
            )
        if not promotion.active:
            return DiscountValidationResult(
                code=promotion.code,
                valid=False,
                reason="inactive",
            )
        return DiscountValidationResult(
            code=promotion.code,
            valid=True,
            discount_percent=promotion.discount_percent,
            reason="active",
        )

    @staticmethod
    def _same(left: str, right: str) -> bool:
        return left.strip().casefold() == right.strip().casefold()
