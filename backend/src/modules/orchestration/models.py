"""Tool interface and related models for the orchestration layer.

This module defines the core data structures for the typed parametric tool system:
- Tool: Interface definition with schema, metadata, and execution contract
- ToolResult: Standardized output format with provenance
- ToolCall: Represents a tool invocation in an agent plan
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CapabilityTag(str, Enum):
    """Tool capability categories for discovery and routing."""

    READ = "read"
    WRITE = "write"
    BATCH = "batch"
    SEARCH = "search"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    EXPORT = "export"
    ANALYSIS = "analysis"


class ToolInputSchema(BaseModel):
    """JSON Schema for tool input validation."""

    type: str = "object"
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolOutputSchema(BaseModel):
    """JSON Schema for tool output structure."""

    type: str = "object"
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)


@dataclass
class Tool:
    """Typed parametric tool interface.

    Every capability exposed to the agent must implement this interface.
    The schema must be serializable to OpenAI/Anthropic tool-call format and MCP.
    """

    name: str
    """Tool identifier (snake_case, unique across registry)."""

    description: str
    """Human-readable description of what the tool does (used by LLM)."""

    input_schema: ToolInputSchema
    """JSON Schema for input validation and LLM tool-calling."""

    output_schema: ToolOutputSchema
    """JSON Schema for output structure."""

    capability_tags: set[CapabilityTag]
    """Tags for tool discovery (e.g., {READ, SEARCH})."""

    estimated_cost_seconds: float = 0.0
    """Estimated execution time in seconds for budget planning."""

    is_write: bool = False
    """Whether the tool modifies state (files, database, etc.)."""

    is_batch: bool = False
    """Whether the tool is a long-running async job."""

    idempotency_key: Optional[str] = None
    """Optional key for idempotency (e.g., content hash for write tools)."""

    executor: Optional[Callable[[dict[str, Any]], "ToolResult"]] = None
    """Function that executes the tool logic."""

    def to_openai_tool_dict(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_dump(exclude_none=True),
            },
        }

    def to_anthropic_tool_dict(self) -> dict[str, Any]:
        """Convert to Anthropic tool-use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_dump(exclude_none=True),
        }

    def compute_idempotency_key(self, input_data: dict[str, Any]) -> str:
        """Compute idempotency key from input if not pre-computed."""
        if self.idempotency_key:
            return self.idempotency_key
        # Default: hash of sorted JSON input
        normalized = json.dumps(input_data, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class ToolResult:
    """Standardized tool execution result with provenance."""

    success: bool
    """Whether execution succeeded."""

    output: dict[str, Any] = field(default_factory=dict)
    """Structured output matching tool's output_schema."""

    error: Optional[str] = None
    """Error message if success=False."""

    execution_time_seconds: float = 0.0
    """Actual execution time."""

    citations: list[dict[str, Any]] = field(default_factory=list)
    """Source citations for provenance (section_id, heading, page, etc.)."""

    artifact_path: Optional[str] = None
    """Path to generated artifact file (for export/generation tools)."""

    job_id: Optional[str] = None
    """Job ID for async batch tools."""

    provenance: dict[str, Any] = field(default_factory=dict)
    """Execution metadata (tool_name, input_hash, timestamp, etc.)."""

    @classmethod
    def success_result(
        cls,
        output: dict[str, Any],
        execution_time_seconds: float = 0.0,
        citations: Optional[list[dict[str, Any]]] = None,
        artifact_path: Optional[str] = None,
        job_id: Optional[str] = None,
        tool_name: str = "",
    ) -> "ToolResult":
        """Create a successful result."""
        return cls(
            success=True,
            output=output,
            execution_time_seconds=execution_time_seconds,
            citations=citations or [],
            artifact_path=artifact_path,
            job_id=job_id,
            provenance={
                "tool_name": tool_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        execution_time_seconds: float = 0.0,
        tool_name: str = "",
    ) -> "ToolResult":
        """Create an error result."""
        return cls(
            success=False,
            error=error,
            execution_time_seconds=execution_time_seconds,
            provenance={
                "tool_name": tool_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@dataclass
class ToolCall:
    """Represents a tool invocation in an agent plan."""

    tool_name: str
    """Name of the tool to call."""

    input_data: dict[str, Any]
    """Input parameters for the tool."""

    call_id: str = field(default_factory=lambda: str(uuid4())[:8])
    """Unique identifier for this call within a plan."""

    depends_on: list[str] = field(default_factory=list)
    """List of call_ids this call depends on (for plan sequencing)."""

    estimated_cost_seconds: float = 0.0
    """Estimated execution time from tool definition."""

    result: Optional[ToolResult] = None
    """Result after execution (populated by executor)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for logging/serialization."""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "input_data": self.input_data,
            "depends_on": self.depends_on,
            "estimated_cost_seconds": self.estimated_cost_seconds,
        }
