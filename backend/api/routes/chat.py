"""Conversation and chat message routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import (
    ChatReplyResponse,
    ConversationSummary,
    CreateConversationRequest,
    MessageResponse,
    SendMessageRequest,
)
from auth.dependencies import get_current_user
from services.chat_service import ChatService
from storage.user_repository import ConversationRepository, MessageRepository, UserRecord

router = APIRouter(tags=["chat"])


def _to_reply(result: dict[str, Any]) -> ChatReplyResponse:
    if "assistant_message" not in result:
        raise HTTPException(status_code=400, detail=result.get("content", "Unknown error"))
    am = result["assistant_message"]
    return ChatReplyResponse(
        assistant_message=MessageResponse(**am),
        docx_available=result.get("docx_available", False),
        docx_download_url=result.get("docx_download_url"),
    )


@router.post("/conversations", response_model=ConversationSummary)
def create_conversation(
    body: CreateConversationRequest,
    current: UserRecord = Depends(get_current_user),
):
    conv = ConversationRepository().create(current.user_id, body.book_id, body.title)
    return ConversationSummary(
        conversation_id=conv.conversation_id,
        book_id=conv.book_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(current: UserRecord = Depends(get_current_user)):
    rows = ConversationRepository().list_for_user(current.user_id)
    return [
        ConversationSummary(
            conversation_id=c.conversation_id,
            book_id=c.book_id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(conversation_id: str, current: UserRecord = Depends(get_current_user)):
    conv = ConversationRepository().get(conversation_id, current.user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = MessageRepository().list_for_conversation(conversation_id)
    return [
        MessageResponse(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            export_id=m.export_id,
            metadata=m.metadata,
            created_at=m.created_at,
        )
        for m in msgs
    ]


@router.post("/conversations/{conversation_id}/messages", response_model=ChatReplyResponse)
def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    current: UserRecord = Depends(get_current_user),
):
    conv = ConversationRepository().get(conversation_id, current.user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        result = ChatService().send_message(current.user_id, conversation_id, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_reply(result)


@router.post("/conversations/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: str,
    body: SendMessageRequest,
    current: UserRecord = Depends(get_current_user),
):
    conv = ConversationRepository().get(conversation_id, current.user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    queue: asyncio.Queue[tuple[str, dict[str, Any] | None]] = asyncio.Queue()

    def on_status(stage: str, detail: dict[str, Any] | None = None) -> None:
        queue.put_nowait((stage, detail))

    async def run_chat() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                ChatService().send_message,
                current.user_id,
                conversation_id,
                body.content,
                on_status=on_status,
            )
        except ValueError as exc:
            return {"error": str(exc)}

    async def event_generator():
        task = asyncio.create_task(run_chat())
        while not task.done() or not queue.empty():
            try:
                stage, detail = await asyncio.wait_for(queue.get(), timeout=0.25)
                payload = json.dumps({"stage": stage, "detail": detail})
                yield f"event: status\ndata: {payload}\n\n"
            except asyncio.TimeoutError:
                if task.done():
                    break
                continue

        result = await task
        if "error" in result:
            yield f"event: error\ndata: {json.dumps({'detail': result['error']})}\n\n"
        else:
            yield f"event: done\ndata: {json.dumps(result)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
