"""Process-local conversation state, turn counters, and per-session leases."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from salesagent.domain.conversation import MAX_HISTORY_TURNS, SessionState


class SessionLease:
    """Exclusive snapshot and one-shot commit capability for one session turn."""

    def __init__(
        self,
        *,
        repository: "InMemorySessionRepository",
        session_id: str,
        turn_index: int,
        state: SessionState,
    ) -> None:
        self._repository = repository
        self.session_id = session_id
        self.turn_index = turn_index
        self.state = state
        self._active = True
        self._committed = False

    def commit(self, state: SessionState) -> None:
        """Replace the session snapshot once while this lease remains active."""
        if not self._active:
            raise RuntimeError("session lease is no longer active")
        if self._committed:
            raise RuntimeError("session lease has already committed")
        if len(state.history) > MAX_HISTORY_TURNS:
            raise ValueError("session history exceeds its configured bound")
        self._repository._commit(self.session_id, state)
        self._committed = True

    def _close(self) -> None:
        self._active = False


class InMemorySessionRepository:
    """Own immutable session snapshots and serialize same-session turns."""

    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}
        self._turn_indices: dict[str, int] = {}
        self._session_locks: dict[str, Lock] = {}
        self._registry_lock = Lock()

    @contextmanager
    def lease(self, session_id: str) -> Iterator[SessionLease]:
        """Reserve a turn and hold that session's lock through commit or rollback."""
        session_lock = self._lock_for(session_id)
        with session_lock:
            turn_index = self._turn_indices.get(session_id, 0) + 1
            self._turn_indices[session_id] = turn_index
            lease = SessionLease(
                repository=self,
                session_id=session_id,
                turn_index=turn_index,
                state=self._states.get(session_id, SessionState()),
            )
            try:
                yield lease
            finally:
                lease._close()

    def get_state(self, session_id: str) -> SessionState:
        """Return an immutable current snapshot for diagnostics and tests."""
        session_lock = self._lock_for(session_id)
        with session_lock:
            return self._states.get(session_id, SessionState())

    def _lock_for(self, session_id: str) -> Lock:
        with self._registry_lock:
            return self._session_locks.setdefault(session_id, Lock())

    def _commit(self, session_id: str, state: SessionState) -> None:
        self._states[session_id] = state
