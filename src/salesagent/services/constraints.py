"""Deterministic normalization and merge rules for shopper constraints."""

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Literal

from salesagent.agent.final_output import ConstraintUpdates
from salesagent.domain.conversation import ResolvedConstraintState

ConstraintField = Literal[
    "category",
    "activity",
    "weather",
    "features",
    "maximum_price",
    "colour",
    "size",
    "season",
    "priority",
]
ConstraintValue = str | tuple[str, ...] | Decimal | None

CONSTRAINT_FIELD_ORDER: tuple[ConstraintField, ...] = (
    "category",
    "activity",
    "weather",
    "features",
    "maximum_price",
    "colour",
    "size",
    "season",
    "priority",
)


@dataclass(frozen=True, slots=True)
class ConstraintStateChange:
    """One semantic old-to-new field transition."""

    field: ConstraintField
    previous: ConstraintValue
    current: ConstraintValue


@dataclass(frozen=True, slots=True)
class ConstraintMergeResult:
    """Proposed immutable state and fixed-order semantic changes."""

    state: ResolvedConstraintState
    changes: tuple[ConstraintStateChange, ...]


class ConstraintStateMerger:
    """Apply a validated retain/set/clear patch without mutating old state."""

    def merge(
        self,
        old: ResolvedConstraintState,
        updates: ConstraintUpdates,
    ) -> ConstraintMergeResult:
        """Return a fully normalized proposed state and semantic change evidence."""
        proposed = replace(
            old,
            category=_merge_text(old.category, updates.category),
            activity=_merge_text(old.activity, updates.activity),
            weather=_merge_text_list(old.weather, updates.weather),
            features=_merge_text_list(old.features, updates.features),
            maximum_price=_merge_money(old.maximum_price, updates.maximum_price),
            colour=_merge_text(old.colour, updates.colour),
            size=_merge_text(old.size, updates.size),
            season=_merge_text(old.season, updates.season),
            priority=_merge_text(old.priority, updates.priority),
        )
        changes = tuple(
            ConstraintStateChange(
                field=field,
                previous=getattr(old, field),
                current=getattr(proposed, field),
            )
            for field in CONSTRAINT_FIELD_ORDER
            if getattr(old, field) != getattr(proposed, field)
        )
        return ConstraintMergeResult(state=proposed, changes=changes)


def normalize_text(value: str) -> str:
    """Trim and collapse every whitespace run to one ASCII space."""
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("constraint text cannot be blank")
    return normalized


def _merge_text(old: str | None, update: object) -> str | None:
    if update is None:
        return old
    operation = getattr(update, "operation", None)
    value = getattr(update, "value", None)
    if operation == "clear" and value is None:
        return None
    if operation != "set" or not isinstance(value, str):
        raise ValueError("invalid text constraint update")
    normalized = normalize_text(value)
    if old is not None and old.casefold() == normalized.casefold():
        return old
    return normalized


def _merge_text_list(old: tuple[str, ...], update: object) -> tuple[str, ...]:
    if update is None:
        return old
    operation = getattr(update, "operation", None)
    value = getattr(update, "value", None)
    if operation == "clear" and value is None:
        return ()
    if operation != "set" or not isinstance(value, tuple) or not value:
        raise ValueError("invalid list constraint update")

    normalized_by_key: dict[str, str] = {}
    for item in value:
        if not isinstance(item, str):
            raise ValueError("invalid list constraint item")
        normalized = normalize_text(item)
        normalized_by_key.setdefault(normalized.casefold(), normalized)
    normalized_values = tuple(
        normalized_by_key[key] for key in sorted(normalized_by_key)
    )
    if {item.casefold() for item in old} == set(normalized_by_key):
        return old
    return normalized_values


def _merge_money(old: Decimal | None, update: object) -> Decimal | None:
    if update is None:
        return old
    operation = getattr(update, "operation", None)
    value = getattr(update, "value", None)
    if operation == "clear" and value is None:
        return None
    if operation != "set" or not isinstance(value, str):
        raise ValueError("invalid maximum-price update")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("maximum price must be a decimal string") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("maximum price must be finite and nonnegative")
    if old is not None and old == amount:
        return old
    return amount
