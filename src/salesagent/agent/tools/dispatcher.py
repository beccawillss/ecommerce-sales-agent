"""Allowlisted deterministic dispatcher for read-only commerce tools."""

from collections.abc import Mapping
from time import perf_counter_ns
from typing import Literal

from pydantic import BaseModel, ValidationError

from salesagent.agent.tools.definitions import get_tool_spec
from salesagent.agent.tools.models import (
    CheckInventoryArguments,
    DiscountData,
    GetProductArguments,
    InventoryData,
    ProductData,
    SearchProductsArguments,
    SearchProductsData,
    ToolExecutionError,
    ToolExecutionResult,
    ValidateDiscountArguments,
)
from salesagent.agent.tools.serialization import serialize_model
from salesagent.services.commerce import CommerceService


class ToolDispatcher:
    """Validate and execute only the four registered read-only tools."""

    def __init__(self, commerce_service: CommerceService) -> None:
        self._commerce = commerce_service

    def dispatch(
        self,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> ToolExecutionResult:
        """Dispatch one validated tool call without exposing raw exceptions."""
        started_at = perf_counter_ns()
        spec = get_tool_spec(tool_name)
        if spec is None:
            return self._failure(
                tool_name=tool_name,
                code="unknown_tool",
                message="Unknown tool name.",
                duration_ms=self._elapsed_ms(started_at),
            )

        try:
            validated = spec.argument_model.model_validate(arguments)
        except ValidationError:
            return self._failure(
                tool_name=tool_name,
                code="invalid_arguments",
                message="Arguments did not match the tool schema.",
                duration_ms=self._elapsed_ms(started_at),
            )

        serialized_arguments = serialize_model(validated)
        try:
            data = self._execute(tool_name, validated)
        except Exception:
            return self._failure(
                tool_name=tool_name,
                code="execution_error",
                message="Tool execution failed.",
                arguments=serialized_arguments,
                duration_ms=self._elapsed_ms(started_at),
            )

        if data is None:
            return self._failure(
                tool_name=tool_name,
                code="product_not_found",
                message="Product was not found.",
                arguments=serialized_arguments,
                duration_ms=self._elapsed_ms(started_at),
            )
        return ToolExecutionResult(
            tool_name=tool_name,
            success=True,
            arguments=serialized_arguments,
            data=serialize_model(data),
            error=None,
            duration_ms=self._elapsed_ms(started_at),
        )

    def _execute(self, tool_name: str, arguments: BaseModel) -> BaseModel | None:
        if tool_name == "search_products" and isinstance(
            arguments, SearchProductsArguments
        ):
            products = self._commerce.search_products(arguments)
            product_data = tuple(
                ProductData.from_domain(product) for product in products
            )
            return SearchProductsData(products=product_data, count=len(product_data))

        if tool_name == "get_product" and isinstance(arguments, GetProductArguments):
            product = self._commerce.get_product(arguments.product_id)
            return ProductData.from_domain(product) if product is not None else None

        if tool_name == "check_inventory" and isinstance(
            arguments, CheckInventoryArguments
        ):
            inventory_result = self._commerce.check_inventory(
                arguments.product_id,
                arguments.colour,
                arguments.size,
            )
            return InventoryData.from_domain(inventory_result)

        if tool_name == "validate_discount" and isinstance(
            arguments, ValidateDiscountArguments
        ):
            discount_result = self._commerce.validate_discount(arguments.code)
            return DiscountData.from_domain(discount_result)

        raise RuntimeError("tool registry and dispatcher are inconsistent")

    @staticmethod
    def _failure(
        *,
        tool_name: str,
        code: Literal[
            "unknown_tool",
            "invalid_arguments",
            "product_not_found",
            "execution_error",
        ],
        message: str,
        duration_ms: int,
        arguments: dict[str, object] | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            success=False,
            arguments=arguments,
            data=None,
            error=ToolExecutionError(code=code, message=message),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _elapsed_ms(started_at: int) -> int:
        return (perf_counter_ns() - started_at) // 1_000_000
