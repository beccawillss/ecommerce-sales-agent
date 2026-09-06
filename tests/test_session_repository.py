"""Tests for process-local session state, turn reservation, and locking."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

import pytest

from salesagent.domain.conversation import ConversationTurn, ResolvedConstraintState
from salesagent.repositories.sessions import InMemorySessionRepository


def test_sessions_start_empty_and_commit_in_isolation() -> None:
    repository = InMemorySessionRepository()

    with repository.lease("session-a") as lease_a:
        assert lease_a.turn_index == 1
        assert lease_a.state.resolved_constraints == ResolvedConstraintState()
        lease_a.commit(lease_a.state.append_turn(ConversationTurn("A", "A response")))
    with repository.lease("session-b") as lease_b:
        assert lease_b.turn_index == 1
        assert lease_b.state.history == ()
        lease_b.commit(lease_b.state.append_turn(ConversationTurn("B", "B response")))

    assert repository.get_state("session-a").history[0].user_message == "A"
    assert repository.get_state("session-b").history[0].user_message == "B"


def test_failed_lease_consumes_index_without_mutating_state() -> None:
    repository = InMemorySessionRepository()

    with repository.lease("session") as failed:
        assert failed.turn_index == 1
    with repository.lease("session") as success:
        assert success.turn_index == 2
        assert success.state.history == ()
        success.commit(
            success.state.append_turn(ConversationTurn("success", "complete"))
        )

    assert repository.get_state("session").history[0].user_message == "success"


def test_committed_snapshots_are_immutable_and_history_is_bounded() -> None:
    repository = InMemorySessionRepository()
    constraints = ResolvedConstraintState(maximum_price=Decimal("160.00"))

    for index in range(8):
        with repository.lease("session") as lease:
            state = lease.state.append_turn(
                ConversationTurn(f"user-{index}", f"assistant-{index}")
            )
            lease.commit(
                type(state)(resolved_constraints=constraints, history=state.history)
            )

    snapshot = repository.get_state("session")
    assert [turn.user_message for turn in snapshot.history] == [
        "user-2",
        "user-3",
        "user-4",
        "user-5",
        "user-6",
        "user-7",
    ]
    assert snapshot.resolved_constraints.maximum_price == Decimal("160.00")


def test_lease_rejects_double_commit_and_commit_after_release() -> None:
    repository = InMemorySessionRepository()

    with repository.lease("session") as lease:
        lease.commit(lease.state)
        with pytest.raises(RuntimeError, match="already committed"):
            lease.commit(lease.state)

    with pytest.raises(RuntimeError, match="no longer active"):
        lease.commit(lease.state)


def test_same_session_waits_but_different_session_enters_independently() -> None:
    repository = InMemorySessionRepository()
    first_entered = Event()
    release_first = Event()
    same_entered = Event()
    other_entered = Event()

    def first() -> None:
        with repository.lease("shared") as lease:
            first_entered.set()
            assert release_first.wait(timeout=2)
            lease.commit(lease.state.append_turn(ConversationTurn("first", "complete")))

    def same() -> None:
        assert first_entered.wait(timeout=2)
        with repository.lease("shared") as lease:
            same_entered.set()
            assert lease.turn_index == 2
            assert lease.state.history[-1].user_message == "first"

    def other() -> None:
        assert first_entered.wait(timeout=2)
        with repository.lease("other") as lease:
            other_entered.set()
            assert lease.turn_index == 1

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(first),
            executor.submit(same),
            executor.submit(other),
        ]
        assert first_entered.wait(timeout=2)
        assert other_entered.wait(timeout=2)
        assert not same_entered.is_set()
        release_first.set()
        for future in futures:
            future.result(timeout=2)

    assert same_entered.is_set()
