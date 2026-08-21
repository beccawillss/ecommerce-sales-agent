"""Validated JSON-backed promotion repository."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from salesagent.domain.models import Promotion


class PromotionDataError(ValueError):
    """Raised when promotion data cannot be loaded safely."""


class _PromotionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    promotions: tuple[Promotion, ...]

    @model_validator(mode="after")
    def promotion_codes_are_unique(self) -> "_PromotionDocument":
        codes = {promotion.code.casefold() for promotion in self.promotions}
        if len(codes) != len(self.promotions):
            raise ValueError("promotion codes must be unique")
        return self


class PromotionRepository:
    """Load and retrieve authoritative promotion definitions."""

    def __init__(self, path: Path) -> None:
        promotions = self._load(path)
        self._promotions = tuple(
            sorted(promotions, key=lambda promotion: promotion.code.casefold())
        )
        self._promotions_by_code = {
            promotion.code.casefold(): promotion for promotion in self._promotions
        }

    @staticmethod
    def _load(path: Path) -> tuple[Promotion, ...]:
        try:
            document = _PromotionDocument.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValidationError) as error:
            raise PromotionDataError(
                f"unable to load promotion data from {path}"
            ) from error
        return document.promotions

    def get(self, code: str) -> Promotion | None:
        """Return a promotion using case-insensitive code lookup."""
        return self._promotions_by_code.get(code.strip().casefold())

    def all(self) -> tuple[Promotion, ...]:
        """Return all promotions in canonical code order."""
        return self._promotions
