"""Immutable backend-owned conversation state values."""

from dataclasses import dataclass, replace
from decimal import Decimal

MAX_HISTORY_TURNS = 6


@dataclass(frozen=True, slots=True)
class ResolvedConstraintState:
    """Complete normalized shopper-constraint state for one session."""

    category: str | None = None
    activity: str | None = None
    weather: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    maximum_price: Decimal | None = None
    colour: str | None = None
    size: str | None = None
    season: str | None = None
    priority: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """Minimal successful turn retained for bounded semantic replay."""

    user_message: str
    assistant_message: str
    recommended_product_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionState:
    """Immutable snapshot replaced atomically after a successful turn."""

    resolved_constraints: ResolvedConstraintState = ResolvedConstraintState()
    history: tuple[ConversationTurn, ...] = ()

    def append_turn(self, turn: ConversationTurn) -> "SessionState":
        """Return a snapshot retaining only the six newest complete turns."""
        return replace(self, history=(*self.history, turn)[-MAX_HISTORY_TURNS:])
