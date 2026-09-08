"""Research chat endpoint - agentic chat with SSE streaming.

Provides the /api/research/chat endpoint that uses the ResearchAgent for
agentic workflows with streaming of plan steps, tool calls, and results.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth.dependencies import get_current_user
from auth.jwt_utils import decode_access_token
from src.modules.orchestration.research_agent import ResearchAgent
from storage.user_repository import UserRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


class ChatMessage(BaseModel):
    """Chat message from the client."""

    content: str
    conversation_id: str | None = None


class ApprovalRequest(BaseModel):
    """Plan approval request."""

    plan_id: str
    approved: bool


async def stream_agent_response(
    query: str,
    conversation_history: list[dict[str, str]],
    user_id: str,
) -> AsyncGenerator[str, None]:
    """Stream agent execution with SSE events.

    Args:
        query: User query.
        conversation_history: Previous conversation turns.
        user_id: User ID for provenance.

    Yields:
        SSE-formatted event strings.
    """
    agent = ResearchAgent(user_id=user_id)

    # Emit start event
    yield f"event: status\ndata: {json.dumps({'stage': 'planning', 'message': 'Generating plan...'})}\n\n"

    # Generate plan
    plan = agent.plan(query, conversation_history)

    # Emit plan event
    plan_data = agent.present_plan(plan)
    yield f"event: plan\ndata: {json.dumps(plan_data)}\n\n"

    # Check if plan requires approval
    if plan.requires_approval and not plan.approved:
        yield f"event: approval_required\ndata: {json.dumps({'plan_id': plan.plan_id, 'message': 'Plan requires approval'})}\n\n"
        return

    # Emit execution start
    yield f"event: status\ndata: {json.dumps({'stage': 'executing', 'message': 'Executing plan...'})}\n\n"

    # Execute plan
    result = agent.execute_plan(plan, query, require_approval=True)

    # Stream step-by-step progress
    for step in result.steps:
        step_data = {
            "step_number": step.step_number,
            "reasoning": step.reasoning,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "input_data": tc.input_data,
                }
                for tc in step.tool_calls
            ],
            "observations": step.observations,
        }
        yield f"event: step\ndata: {json.dumps(step_data)}\n\n"

    # Emit final result
    final_data = {
        "success": result.success,
        "final_answer": result.final_answer,
        "total_cost_seconds": result.total_cost_seconds,
        "tool_count": len(result.tool_results),
    }
    yield f"event: done\ndata: {json.dumps(final_data)}\n\n"


@router.post("/chat")
async def research_chat(
    message: ChatMessage,
    current_user: UserRecord = Depends(get_current_user),
) -> StreamingResponse:
    """Agentic chat endpoint with SSE streaming.

    Returns a stream of SSE events including:
    - status: Planning/execution stage updates
    - plan: Generated plan with tool calls and cost estimate
    - approval_required: If plan needs user approval
    - step: Individual execution step with tool calls and observations
    - done: Final result with answer

    Args:
        message: Chat message with content and optional conversation_id.
        current_user: Authenticated user.

    Returns:
        StreamingResponse with SSE events.
    """
    # Build conversation history (in production, this would be fetched from storage)
    conversation_history = []

    async def event_generator():
        try:
            async for chunk in stream_agent_response(
                query=message.content,
                conversation_history=conversation_history,
                user_id=current_user.user_id,
            ):
                yield chunk
        except Exception as exc:
            logger.exception("Agent execution failed: %s", exc)
            error_data = {"error": str(exc), "success": False}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/approve")
async def approve_plan(
    request: ApprovalRequest,
    current_user: UserRecord = Depends(get_current_user),
) -> dict:
    """Approve or reject a pending plan.

    Args:
        request: Approval request with plan_id and approved flag.
        current_user: Authenticated user.

    Returns:
        Confirmation response.
    """
    # In production, this would look up the plan from a store
    # For now, we'll use a simple in-memory approach
    # The actual plan approval state is managed in the agent session
    # This endpoint would be called by the frontend after presenting the plan

    return {
        "plan_id": request.plan_id,
        "approved": request.approved,
        "message": "Plan approved" if request.approved else "Plan rejected",
    }
