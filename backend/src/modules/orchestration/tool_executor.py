"""Tool executor for running parametric tools with validation and provenance."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from src.modules.orchestration.models import Tool, ToolResult

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class ToolExecutor:
    """Executes parametric tools with validation and provenance tracking."""

    def __init__(self, artifact_dir: Optional[Path] = None) -> None:
        """Initialize the tool executor.

        Args:
            artifact_dir: Directory for storing tool-generated artifacts.
        """
        self.artifact_dir = artifact_dir or Path("output/tool_artifacts")
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def validate_input(self, tool: Tool, input_data: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate input data against the tool's schema.

        Args:
            tool: Tool instance.
            input_data: Input data to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        try:
            tool.input_schema.model_validate(input_data)
            return True, None
        except ValidationError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"Validation error: {exc}"

    def execute(self, tool: Tool, input_data: dict[str, Any], user_id: Optional[str] = None) -> ToolResult:
        """Execute a tool with validation and provenance tracking.

        Args:
            tool: Tool instance to execute.
            input_data: Input parameters for the tool.
            user_id: Optional user ID for provenance.

        Returns:
            ToolResult with output, citations, and provenance metadata.
        """
        start_time = time.time()

        # Validate input
        is_valid, error_msg = self.validate_input(tool, input_data)
        if not is_valid:
            logger.error("Input validation failed for tool %s: %s", tool.name, error_msg)
            return ToolResult.error_result(
                error=f"Input validation failed: {error_msg}",
                execution_time_seconds=time.time() - start_time,
                tool_name=tool.name,
            )

        # Check for idempotency (optional enhancement)
        idempotency_key = tool.compute_idempotency_key(input_data)

        # Execute the tool
        try:
            if tool.executor is None:
                return ToolResult.error_result(
                    error=f"Tool '{tool.name}' has no executor function",
                    execution_time_seconds=time.time() - start_time,
                    tool_name=tool.name,
                )

            result = tool.executor(input_data)
            execution_time = time.time() - start_time

            executor_provenance = {
                "input_hash": idempotency_key,
                "user_id": user_id,
                "is_write": tool.is_write,
                "is_batch": tool.is_batch,
            }

            # Tools return a fully-formed ToolResult; pass it through, enriching
            # provenance and backfilling execution time. Re-wrapping here would
            # bury the tool's own ToolResult inside output (breaking JSON
            # serialization) and mislabel error results as successes.
            if isinstance(result, ToolResult):
                if not result.execution_time_seconds:
                    result.execution_time_seconds = execution_time
                result.provenance = {**executor_provenance, **(result.provenance or {})}
                return result

            # Fallback for tools that return a raw payload instead of a ToolResult.
            if not isinstance(result, dict):
                result = {"output": result}
            citations = result.pop("citations", [])
            artifact_path = result.pop("artifact_path", None)
            job_id = result.pop("job_id", None)

            tool_result = ToolResult.success_result(
                output=result,
                execution_time_seconds=execution_time,
                citations=citations,
                artifact_path=artifact_path,
                job_id=job_id,
                tool_name=tool.name,
            )
            tool_result.provenance = {**executor_provenance, **tool_result.provenance}
            return tool_result

        except Exception as exc:
            logger.exception("Tool execution failed for %s: %s", tool.name, exc)
            return ToolResult.error_result(
                error=f"Tool execution failed: {str(exc)}",
                execution_time_seconds=time.time() - start_time,
                tool_name=tool.name,
            )

    def execute_tool_call(self, tool_name: str, input_data: dict[str, Any], user_id: Optional[str] = None) -> ToolResult:
        """Execute a tool by name (convenience method).

        Args:
            tool_name: Name of the tool to execute.
            input_data: Input parameters for the tool.
            user_id: Optional user ID for provenance.

        Returns:
            ToolResult from execution.

        Raises:
            ValueError: If tool is not found in registry.
        """
        from src.modules.orchestration.tool_registry import get_global_registry

        registry = get_global_registry()
        tool = registry.get(tool_name)

        if tool is None:
            return ToolResult.error_result(
                error=f"Tool '{tool_name}' not found in registry",
                tool_name=tool_name,
            )

        return self.execute(tool, input_data, user_id=user_id)


# Global executor instance
_global_executor: Optional[ToolExecutor] = None


def get_global_executor() -> ToolExecutor:
    """Get the global tool executor singleton.

    Returns:
        Global ToolExecutor instance.
    """
    global _global_executor
    if _global_executor is None:
        _global_executor = ToolExecutor()
    return _global_executor
