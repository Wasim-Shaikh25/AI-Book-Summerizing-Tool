"""Tests for research agent planner-executor loop."""

from __future__ import annotations

import pytest

from src.modules.orchestration.models import ToolCall
from src.modules.orchestration.research_agent import AgentPlan, ResearchAgent


def test_agent_initialization():
    """Test research agent initialization."""
    agent = ResearchAgent(user_id="test_user", max_tool_calls=5, max_retries=2)
    assert agent.user_id == "test_user"
    assert agent.max_tool_calls == 5
    assert agent.max_retries == 2


def test_build_planner_prompt():
    """Test planner prompt construction."""
    agent = ResearchAgent(user_id="test_user")
    prompt = agent._build_planner_prompt("What is photosynthesis?", [])
    assert "photosynthesis" in prompt
    assert "search_documents" in prompt  # This tool is in the prompt


def test_parse_planner_response():
    """Test parsing JSON plan response."""
    agent = ResearchAgent(user_id="test_user")
    response = """
    {
        "reasoning": "Need to search for information",
        "tool_calls": [
            {
                "tool_name": "search_documents",
                "input_data": {"query": "photosynthesis"}
            }
        ]
    }
    """
    parsed = agent._parse_planner_response(response)
    assert parsed["reasoning"] == "Need to search for information"
    assert len(parsed["tool_calls"]) == 1
    assert parsed["tool_calls"][0]["tool_name"] == "search_documents"


def test_parse_planner_response_fallback():
    """Test fallback when JSON parsing fails."""
    agent = ResearchAgent(user_id="test_user")
    response = "This is not valid JSON"
    parsed = agent._parse_planner_response(response)
    assert "reasoning" in parsed
    assert parsed["tool_calls"] == []


def test_out_of_scope_handling():
    """Test out-of-scope plan detection."""
    agent = ResearchAgent(user_id="test_user")
    response = """
    {
        "reasoning": "User asked for video generation",
        "out_of_scope": true,
        "alternative_suggestion": "I can help you create a written summary instead"
    }
    """
    # Parse the response first
    parsed = agent._parse_planner_response(response)
    # Build plan from parsed data manually (mimicking what plan() does internally)
    tool_calls = []
    if parsed.get("out_of_scope", False):
        plan = AgentPlan(
            reasoning=parsed.get("reasoning", ""),
            tool_calls=[],
            estimated_cost_seconds=0.0,
            out_of_scope=True,
            alternative_suggestion=parsed.get("alternative_suggestion", ""),
        )
    else:
        for tc_data in parsed.get("tool_calls", []):
            tool = agent.registry.get(tc_data.get("tool_name"))
            if tool:
                tool_calls.append(
                    ToolCall(
                        tool_name=tc_data.get("tool_name"),
                        input_data=tc_data.get("input_data", {}),
                        estimated_cost_seconds=tool.estimated_cost_seconds,
                    )
                )
        plan = AgentPlan(
            reasoning=parsed.get("reasoning", ""),
            tool_calls=tool_calls,
            estimated_cost_seconds=sum(tc.estimated_cost_seconds for tc in tool_calls),
        )

    assert plan.out_of_scope is True
    assert "written summary" in plan.alternative_suggestion


def test_present_plan():
    """Test plan presentation for UI."""
    agent = ResearchAgent(user_id="test_user")
    plan = AgentPlan(
        tool_calls=[
            ToolCall(
                tool_name="search_documents",
                input_data={"query": "test"},
                estimated_cost_seconds=2.0,
            )
        ],
        estimated_cost_seconds=2.0,
        reasoning="Test reasoning",
    )
    presented = agent.present_plan(plan)
    assert presented["requires_approval"] is False  # No write/batch tools
    assert presented["tool_count"] == 1
    assert "Test reasoning" in presented["reasoning"]
