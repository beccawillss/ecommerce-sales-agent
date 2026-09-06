"""Shared application-boundary test doubles for offline agent tests."""

from collections.abc import Iterable

from salesagent.agent.final_output import AgentFinalOutput, ConstraintUpdates
from salesagent.agent.responses_client import (
    ModelResponse,
    ResponseRequest,
    ResponsesClient,
    ResponsesClientError,
)


def final_output_json(
    message: str,
    nominated_product_ids: Iterable[str] = (),
    constraint_updates: ConstraintUpdates | None = None,
    nominated_promotion_code: str | None = None,
) -> str:
    """Build valid strict final output without teaching the fake to parse it."""
    return AgentFinalOutput(
        message=message,
        nominated_product_ids=tuple(nominated_product_ids),
        nominated_promotion_code=nominated_promotion_code,
        constraint_updates=constraint_updates or ConstraintUpdates.retain_all(),
    ).model_dump_json()


class ScriptedResponsesClient(ResponsesClient):
    """Return queued snapshots and retain every application request."""

    def __init__(
        self,
        responses: list[ModelResponse | ResponsesClientError],
    ) -> None:
        self._responses = responses
        self.requests: list[ResponseRequest] = []

    def create_response(self, request: ResponseRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("orchestrator made an unexpected Responses call")
        response = self._responses.pop(0)
        if isinstance(response, ResponsesClientError):
            raise response
        return response
