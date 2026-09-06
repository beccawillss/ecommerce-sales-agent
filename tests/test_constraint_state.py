"""Tests for backend conversation models and deterministic constraint merging."""

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal

import pytest

from salesagent.agent.final_output import (
    ConstraintUpdates,
    MoneyTextUpdate,
    TextListUpdate,
    TextUpdate,
)
from salesagent.domain.conversation import (
    MAX_HISTORY_TURNS,
    ConversationTurn,
    ResolvedConstraintState,
    SessionState,
)
from salesagent.services.constraints import ConstraintStateMerger, normalize_text


def updates(**values: object) -> ConstraintUpdates:
    payload = ConstraintUpdates.retain_all().model_dump()
    payload.update(values)
    return ConstraintUpdates.model_validate(payload)


def test_resolved_constraint_model_has_exact_contract_fields_and_defaults() -> None:
    state = ResolvedConstraintState()

    assert [field.name for field in fields(state)] == [
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
    assert state == ResolvedConstraintState(
        category=None,
        activity=None,
        weather=(),
        features=(),
        maximum_price=None,
        colour=None,
        size=None,
        season=None,
        priority=None,
    )


def test_conversation_models_are_immutable_and_retain_decimal() -> None:
    constraints = ResolvedConstraintState(maximum_price=Decimal("160.00"))
    turn = ConversationTurn("Shopper", "Assistant", ("JKT-001",))
    state = SessionState(resolved_constraints=constraints, history=(turn,))

    assert state.resolved_constraints.maximum_price == Decimal("160.00")
    with pytest.raises(FrozenInstanceError):
        constraints.maximum_price = Decimal("120")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        turn.user_message = "Changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        state.history = ()  # type: ignore[misc]


def test_session_history_helper_keeps_six_newest_complete_turns() -> None:
    state = SessionState()

    for index in range(MAX_HISTORY_TURNS + 2):
        state = state.append_turn(
            ConversationTurn(
                user_message=f"user-{index}",
                assistant_message=f"assistant-{index}",
                recommended_product_ids=(f"ID-{index}",),
            )
        )

    assert len(state.history) == MAX_HISTORY_TURNS
    assert [turn.user_message for turn in state.history] == [
        "user-2",
        "user-3",
        "user-4",
        "user-5",
        "user-6",
        "user-7",
    ]
    assert state.resolved_constraints == ResolvedConstraintState()


def test_normalize_text_collapses_all_whitespace() -> None:
    assert normalize_text("  Ocean\t Blue\n jacket ") == "Ocean Blue jacket"
    with pytest.raises(ValueError):
        normalize_text(" \t\n ")


def test_merge_adds_replaces_clears_and_retains_in_fixed_order() -> None:
    old = ResolvedConstraintState(
        category="Jacket",
        activity="Hiking",
        weather=("Rain",),
        maximum_price=Decimal("160.00"),
        colour="Blue",
        size="M",
    )
    patch = updates(
        category=TextUpdate(operation="set", value=" jacket "),
        activity=TextUpdate(operation="set", value="Trail running"),
        weather=TextListUpdate(operation="set", value=("Wind", " rain ", "WIND")),
        features=TextListUpdate(operation="set", value=("Packable", "breathable")),
        maximum_price=MoneyTextUpdate(operation="set", value="120"),
        colour=TextUpdate(operation="clear", value=None),
        priority=TextUpdate(operation="set", value=" Low weight "),
    )

    result = ConstraintStateMerger().merge(old, patch)

    assert result.state == ResolvedConstraintState(
        category="Jacket",
        activity="Trail running",
        weather=("rain", "Wind"),
        features=("breathable", "Packable"),
        maximum_price=Decimal("120"),
        colour=None,
        size="M",
        priority="Low weight",
    )
    assert [change.field for change in result.changes] == [
        "activity",
        "weather",
        "features",
        "maximum_price",
        "colour",
        "priority",
    ]
    assert result.changes[3].previous == Decimal("160.00")
    assert result.changes[3].current == Decimal("120")
    assert old.colour == "Blue"
    assert old.maximum_price == Decimal("160.00")


def test_merge_preserves_stored_display_values_for_semantic_no_ops() -> None:
    old = ResolvedConstraintState(
        activity="Trail Running",
        weather=("Heavy Rain", "Wind"),
        maximum_price=Decimal("120.00"),
    )
    patch = updates(
        activity=TextUpdate(operation="set", value=" trail   running "),
        weather=TextListUpdate(operation="set", value=("wind", "HEAVY rain", "Wind")),
        maximum_price=MoneyTextUpdate(operation="set", value="120.0"),
    )

    result = ConstraintStateMerger().merge(old, patch)

    assert result.state is not old
    assert result.state == old
    assert result.state.activity == "Trail Running"
    assert result.state.weather == ("Heavy Rain", "Wind")
    assert result.state.maximum_price.as_tuple() == Decimal("120.00").as_tuple()
    assert result.changes == ()


def test_clearing_empty_fields_and_retain_all_are_no_ops() -> None:
    old = ResolvedConstraintState(activity="Hiking")
    cleared = ConstraintStateMerger().merge(
        old,
        updates(
            weather=TextListUpdate(operation="clear", value=None),
            features=TextListUpdate(operation="clear", value=None),
            colour=TextUpdate(operation="clear", value=None),
            maximum_price=MoneyTextUpdate(operation="clear", value=None),
        ),
    )
    retained = ConstraintStateMerger().merge(old, ConstraintUpdates.retain_all())

    assert cleared.state == old
    assert cleared.changes == ()
    assert retained.state == old
    assert retained.changes == ()
