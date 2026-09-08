"""Tests for tool executor with input validation and provenance."""

from __future__ import annotations

import pytest

import json

from src.modules.orchestration.models import Tool, ToolInputSchema, ToolOutputSchema, ToolResult
from src.modules.orchestration.tool_executor import ToolExecutor


def _make_tool(executor):
    return Tool(
        name="tr_tool",
        description="Tool that returns a ToolResult (the real contract)",
        input_schema=ToolInputSchema(properties={}),
        output_schema=ToolOutputSchema(properties={}),
        capability_tags=set(),
        estimated_cost_seconds=1.0,
        executor=executor,
    )


def test_execute_tool_success():
    """Test successful tool execution."""
    def dummy_executor(input_data):
        return {"result": "success"}

    tool = Tool(
        name="test_tool",
        description="Test tool",
        input_schema=ToolInputSchema(properties={"message": {"type": "string"}}),
        output_schema=ToolOutputSchema(properties={}),
        capability_tags=set(),
        estimated_cost_seconds=1.0,
        executor=dummy_executor,
    )

    executor = ToolExecutor()
    result = executor.execute(tool, {"message": "hello"}, user_id="test_user")

    assert result.success
    assert result.output == {"result": "success"}


def test_execute_tool_with_error():
    """Test tool execution that raises an error."""
    def failing_executor(input_data):
        raise ValueError("Tool failed")

    tool = Tool(
        name="failing_tool",
        description="Failing tool",
        input_schema=ToolInputSchema(properties={}),
        output_schema=ToolOutputSchema(properties={}),
        capability_tags=set(),
        estimated_cost_seconds=1.0,
        executor=failing_executor,
    )

    executor = ToolExecutor()
    result = executor.execute(tool, {}, user_id="test_user")

    assert not result.success
    assert result.error is not None
    assert "Tool failed" in result.error


def test_execute_tool_adds_provenance():
    """Test that execution adds provenance metadata."""
    def dummy_executor(input_data):
        return {"result": "ok"}

    tool = Tool(
        name="test_tool",
        description="Test tool",
        input_schema=ToolInputSchema(properties={}),
        output_schema=ToolOutputSchema(properties={}),
        capability_tags=set(),
        estimated_cost_seconds=1.0,
        executor=dummy_executor,
    )

    executor = ToolExecutor()
    result = executor.execute(tool, {}, user_id="test_user")

    assert result.success
    assert result.provenance is not None
    assert result.provenance.get("tool_name") == "test_tool"
    assert "timestamp" in result.provenance


def test_execute_passes_through_toolresult_and_stays_serializable():
    """Tools return a ToolResult; the executor must not re-wrap it.

    Regression: re-wrapping buried the tool's ToolResult inside output, so
    json.dumps(result.output) raised "Object of type ToolResult is not JSON
    serializable" in the agent's answer synthesis.
    """
    def tr_executor(input_data):
        return ToolResult.success_result(
            output={"answer": "42"},
            citations=[{"section_id": "s1"}],
            tool_name="tr_tool",
        )

    result = ToolExecutor().execute(_make_tool(tr_executor), {}, user_id="u1")

    assert result.success
    # Output is the tool's own payload, not {"output": <ToolResult>}
    assert result.output == {"answer": "42"}
    assert result.citations == [{"section_id": "s1"}]
    # The exact call from ResearchAgent._synthesize_answer must not raise
    json.dumps(result.output, indent=2)
    # Executor enriches provenance with its own metadata
    assert "input_hash" in result.provenance


def test_execute_preserves_toolresult_error():
    """A tool returning an error ToolResult must be reported as a failure."""
    def err_executor(input_data):
        return ToolResult.error_result(error="boom", tool_name="tr_tool")

    result = ToolExecutor().execute(_make_tool(err_executor), {}, user_id="u1")

    assert result.success is False
    assert result.error == "boom"
