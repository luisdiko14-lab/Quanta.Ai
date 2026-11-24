from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=60_000)


class ChatRequest(BaseModel):
    model: str = Field(default="auto", min_length=1, max_length=80)
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    stream: bool = True
    temperature: float | None = Field(default=None, ge=0, le=2)
    conversation_id: UUID | None = None
    file_ids: list[UUID] = Field(default_factory=list, max_length=5)


class ConversationTitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
