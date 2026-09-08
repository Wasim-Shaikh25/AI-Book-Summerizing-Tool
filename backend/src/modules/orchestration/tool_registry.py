"""Tool registry for discovering and managing parametric tools."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from src.modules.orchestration.models import CapabilityTag, Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all parametric tools in the system.

    Tools are registered at startup and can be discovered by:
    - Tool name (exact match)
    - Capability tags (e.g., all READ tools, all WRITE tools)
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._by_tag: dict[CapabilityTag, set[str]] = {tag: set() for tag in CapabilityTag}

    def register(self, tool: Tool) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register.

        Raises:
            ValueError: If a tool with the same name already exists.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")

        self._tools[tool.name] = tool
        for tag in tool.capability_tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = set()
            self._by_tag[tag].add(tool.name)

        logger.info("Registered tool: %s (tags: %s)", tool.name, [t.value for t in tool.capability_tags])

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name.

        Args:
            name: Tool name.

        Returns:
            Tool instance if found, None otherwise.
        """
        return self._tools.get(name)

    def get_by_tag(self, tag: CapabilityTag) -> list[Tool]:
        """Get all tools with a specific capability tag.

        Args:
            tag: Capability tag to filter by.

        Returns:
            List of tools with the specified tag.
        """
        tool_names = self._by_tag.get(tag, set())
        return [self._tools[name] for name in tool_names if name in self._tools]

    def list_all(self) -> list[Tool]:
        """List all registered tools.

        Returns:
            List of all tools in registration order.
        """
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names.
        """
        return list(self._tools.keys())

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Export all tools to OpenAI function-calling format.

        Returns:
            List of tool dictionaries for OpenAI API.
        """
        return [tool.to_openai_tool_dict() for tool in self._tools.values()]

    def to_anthropic_tools(self) -> list[dict[str, Any]]:
        """Export all tools to Anthropic tool-use format.

        Returns:
            List of tool dictionaries for Anthropic API.
        """
        return [tool.to_anthropic_tool_dict() for tool in self._tools.values()]


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """Get the global tool registry singleton.

    Returns:
        Global ToolRegistry instance.
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(tool: Tool) -> None:
    """Register a tool in the global registry.

    Convenience function for tool registration modules.

    Args:
        tool: Tool instance to register.
    """
    get_global_registry().register(tool)


def tool(name: str, description: str, capability_tags: list[CapabilityTag], is_write: bool = False, is_batch: bool = False, estimated_cost_seconds: float = 0.0):
    """Decorator for registering tool functions.

    Args:
        name: Tool name.
        description: Tool description.
        capability_tags: List of capability tags.
        is_write: Whether the tool modifies state.
        is_batch: Whether the tool is a long-running async job.
        estimated_cost_seconds: Estimated execution time in seconds.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
        from src.modules.orchestration.models import Tool, ToolInputSchema, ToolOutputSchema

        # Extract schema from function annotations if possible
        # For now, use generic schemas - can be enhanced with inspect
        input_schema = ToolInputSchema()
        output_schema = ToolOutputSchema()

        tool_instance = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            capability_tags=set(capability_tags),
            estimated_cost_seconds=estimated_cost_seconds,
            is_write=is_write,
            is_batch=is_batch,
            executor=lambda input_data: func(input_data),
        )

        register_tool(tool_instance)
        return func

    return decorator
