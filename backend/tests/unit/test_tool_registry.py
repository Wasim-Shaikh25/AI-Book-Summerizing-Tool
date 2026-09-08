"""Tests for tool registry and discovery."""

from __future__ import annotations

import pytest

from src.modules.orchestration.models import CapabilityTag, Tool
from src.modules.orchestration.tool_registry import (
    ToolRegistry,
    get_global_registry,
    register_tool,
)


def test_register_and_get_tool():
    """Test registering a tool and retrieving it."""
    def dummy_executor(input_data):
        return {"result": "ok"}

    tool = Tool(
        name="test_tool",
        description="A test tool",
        input_schema={"properties": {}},
        output_schema={"properties": {}},
        capability_tags={CapabilityTag.READ},
        estimated_cost_seconds=1.0,
        executor=dummy_executor,
    )

    registry = ToolRegistry()
    registry.register(tool)

    retrieved = registry.get("test_tool")
    assert retrieved is not None
    assert retrieved.name == "test_tool"
    assert retrieved.description == "A test tool"


def test_list_tools_by_capability():
    """Test filtering tools by capability tag."""
    def dummy_executor(input_data):
        return {"result": "ok"}

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="read_tool",
            description="Read tool",
            input_schema={"properties": {}},
            output_schema={"properties": {}},
            capability_tags={CapabilityTag.READ},
            estimated_cost_seconds=1.0,
            executor=dummy_executor,
        )
    )
    registry.register(
        Tool(
            name="write_tool",
            description="Write tool",
            input_schema={"properties": {}},
            output_schema={"properties": {}},
            capability_tags={CapabilityTag.WRITE},
            estimated_cost_seconds=1.0,
            executor=dummy_executor,
        )
    )

    read_tools = registry.get_by_tag(CapabilityTag.READ)
    assert len(read_tools) == 1
    assert read_tools[0].name == "read_tool"

    write_tools = registry.get_by_tag(CapabilityTag.WRITE)
    assert len(write_tools) == 1
    assert write_tools[0].name == "write_tool"


def test_get_all_tools():
    """Test getting all registered tools."""
    registry = ToolRegistry()

    for i in range(3):
        registry.register(
            Tool(
                name=f"tool_{i}",
                description=f"Tool {i}",
                input_schema={"properties": {}},
                output_schema={"properties": {}},
                capability_tags=set(),
                estimated_cost_seconds=1.0,
                executor=lambda x: {"result": "ok"},
            )
        )

    all_tools = registry.list_all()
    assert len(all_tools) == 3


def test_tool_not_found():
    """Test retrieving a non-existent tool returns None."""
    registry = ToolRegistry()
    result = registry.get("nonexistent_tool")
    assert result is None


def test_decorator_registers_tool():
    """Test that decorator registers tool in global registry."""
    from src.modules.orchestration.read_tools import list_documents

    global_registry = get_global_registry()
    tool = global_registry.get("list_documents")
    assert tool is not None
    assert tool.name == "list_documents"
