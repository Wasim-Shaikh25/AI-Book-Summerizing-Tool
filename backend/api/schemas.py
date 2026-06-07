"""Pydantic schemas for API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    email: str
    display_name: str
    provider: str
    avatar_url: str | None = None


class BookSummary(BaseModel):
    book_id: str
    title: str
    total_pages: int | None = None
    processed_at: str | None = None
    file_path: str | None = None


class UploadJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class UploadStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str
    book: BookSummary | None = None
    error: str | None = None


class CreateConversationRequest(BaseModel):
    book_id: str
    title: str = "New chat"


class ConversationSummary(BaseModel):
    conversation_id: str
    book_id: str
    title: str
    created_at: str
    updated_at: str


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    export_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ChatReplyResponse(BaseModel):
    assistant_message: MessageResponse
    docx_available: bool = False
    docx_download_url: str | None = None


class AuthConfigResponse(BaseModel):
    auth_enabled: bool
