import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.core.rate_limit import enforce_rate_limit
from app.core.sessions import require_csrf, require_identity
from app.db.models import Conversation, FileAsset, Message
from app.db.session import get_db_session, session_factory
from app.schemas.chat import ChatMessage, ChatRequest, ConversationTitleUpdate
from app.services.ai import complete_chat, provider_status, public_models, stream_chat

router = APIRouter(prefix="/api/v1", tags=["Quanta AI"])
router.include_router(auth_router)
router.include_router(files_router)


def _user_uuid(identity: dict) -> UUID | None:
    value = identity.get("user_id")
    return UUID(str(value)) if value else None


async def _owned_conversation(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


async def _prepare_conversation(
    payload: ChatRequest,
    identity: dict,
    session: AsyncSession,
) -> UUID | None:
    user_id = _user_uuid(identity)
    if not user_id:
        if payload.conversation_id:
            raise HTTPException(status_code=403, detail="Guest conversations are not persistent.")
        return None

    latest_user_message = next(
        (item.content for item in reversed(payload.messages) if item.role == "user"),
        None,
    )
    if latest_user_message is None:
        raise HTTPException(status_code=422, detail="A user message is required.")

    if payload.conversation_id:
        conversation = await _owned_conversation(session, user_id, payload.conversation_id)
    else:
        title = " ".join(latest_user_message.split())[:72] or "New chat"
        conversation = Conversation(
            user_id=user_id,
            title=title,
            model_alias=payload.model,
            is_temporary=False,
        )
        session.add(conversation)
        await session.flush()

    conversation.model_alias = payload.model
    conversation.updated_at = datetime.now(UTC)
    session.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=latest_user_message,
            model_alias=payload.model,
        )
    )
    await session.commit()
    return conversation.id


async def _save_assistant_message(
    user_id: UUID,
    conversation_id: UUID,
    content: str,
    model_alias: str,
) -> None:
    if not content.strip():
        return
    async with session_factory() as session:
        conversation = await _owned_conversation(session, user_id, conversation_id)
        session.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=content,
                model_alias=model_alias,
            )
        )
        conversation.updated_at = datetime.now(UTC)
        await session.commit()


async def _stream_and_record(
    payload: ChatRequest,
    user_id: UUID,
    conversation_id: UUID,
    allow_premium: bool,
) -> AsyncIterator[str]:
    collected: list[str] = []
    async for frame in stream_chat(payload, allow_premium=allow_premium):
        if frame.startswith("data:"):
            data = frame[5:].strip()
            if data and data != "[DONE]":
                try:
                    chunk = json.loads(data)
                    token = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if token:
                        collected.append(token)
                except (ValueError, TypeError, IndexError, AttributeError):
                    pass
        yield frame

    await _save_assistant_message(
        user_id,
        conversation_id,
        "".join(collected),
        payload.model,
    )


@router.get("/models")
async def list_models() -> dict:
    return {"data": public_models()}


@router.get("/providers")
async def list_providers() -> dict:
    return {"data": provider_status()}


@router.get("/conversations")
async def list_conversations(
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user_id = _user_uuid(identity)
    if not user_id:
        return {"data": []}

    conversations = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    return {
        "data": [
            {
                "id": str(item.id),
                "title": item.title,
                "model": item.model_alias,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in conversations
        ]
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: UUID,
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user_id = _user_uuid(identity)
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to access saved conversations.")
    await _owned_conversation(session, user_id, conversation_id)
    messages = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return {
        "conversation_id": str(conversation_id),
        "data": [
            {
                "id": str(item.id),
                "role": item.role,
                "content": item.content,
                "model": item.model_alias,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in messages
        ],
    }


@router.patch(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_csrf)],
)
async def rename_conversation(
    conversation_id: UUID,
    payload: ConversationTitleUpdate,
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user_id = _user_uuid(identity)
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to rename conversations.")
    conversation = await _owned_conversation(session, user_id, conversation_id)
    conversation.title = payload.title.strip()
    conversation.updated_at = datetime.now(UTC)
    await session.commit()
    return {"status": "ok", "id": str(conversation.id), "title": conversation.title}


@router.delete(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_csrf)],
)
async def delete_conversation(
    conversation_id: UUID,
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    user_id = _user_uuid(identity)
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to delete saved conversations.")
    conversation = await _owned_conversation(session, user_id, conversation_id)
    await session.delete(conversation)
    await session.commit()
    return Response(status_code=204)




async def _attach_file_context(
    payload: ChatRequest,
    identity: dict,
    session: AsyncSession,
) -> ChatRequest:
    if not payload.file_ids:
        return payload
    user_id = _user_uuid(identity)
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to use uploaded files in AI chat.")

    assets = await session.scalars(
        select(FileAsset).where(
            FileAsset.user_id == user_id,
            FileAsset.id.in_(payload.file_ids),
        )
    )
    asset_list = list(assets)
    if len({asset.id for asset in asset_list}) != len(set(payload.file_ids)):
        raise HTTPException(status_code=404, detail="One or more attached files were not found.")

    excerpts = []
    for asset in asset_list:
        if asset.extracted_text:
            excerpts.append(
                f"--- Attached file: {asset.original_filename} ---\\n{asset.extracted_text}"
            )
    if not excerpts:
        return payload

    user_messages = list(payload.messages)
    last_user_index = next(
        (index for index in range(len(user_messages) - 1, -1, -1)
         if user_messages[index].role == "user"),
        None,
    )
    if last_user_index is None:
        raise HTTPException(status_code=422, detail="A user message is required.")
    context = "\\n\\n".join(excerpts)[:120_000]
    original = user_messages[last_user_index]
    user_messages[last_user_index] = ChatMessage(
        role="user",
        content=(
            f"{original.content}\\n\\n"
            "Use the following private uploaded-file content as context when relevant:\\n\\n"
            f"{context}"
        )[:180_000],
    )
    return payload.model_copy(update={"messages": user_messages, "file_ids": []})


@router.post(
    "/chat/completions",
    dependencies=[Depends(enforce_rate_limit), Depends(require_csrf)],
)
async def chat_completions(
    payload: ChatRequest,
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    premium_access = (
        identity.get("role") == "admin"
        or identity.get("plan") in {"premium", "pro", "lifetime_premium"}
    )
    if payload.model != "auto":
        chosen = next(
            (model for model in public_models() if model["id"] == payload.model),
            None,
        )
        if chosen and chosen["access"] == "premium" and not premium_access:
            raise HTTPException(
                status_code=403,
                detail="This model requires a Premium or Pro membership.",
            )

    conversation_id = await _prepare_conversation(payload, identity, session)
    provider_payload = await _attach_file_context(payload, identity, session)
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    if conversation_id:
        headers["X-Conversation-ID"] = str(conversation_id)
        headers["Access-Control-Expose-Headers"] = "X-Conversation-ID"

    if payload.stream:
        if conversation_id:
            user_id = _user_uuid(identity)
            if user_id is None:
                raise HTTPException(status_code=403, detail="Sign in to save chat history.")
            response_stream = _stream_and_record(
                provider_payload, user_id, conversation_id, premium_access
            )
        else:
            response_stream = stream_chat(provider_payload, allow_premium=premium_access)
        return StreamingResponse(
            response_stream,
            media_type="text/event-stream",
            headers=headers,
        )

    result = await complete_chat(provider_payload, allow_premium=premium_access)
    if conversation_id:
        user_id = _user_uuid(identity)
        if user_id is not None:
            await _save_assistant_message(
                user_id,
                conversation_id,
                result["choices"][0]["message"]["content"],
                payload.model,
            )
        result["conversation_id"] = str(conversation_id)
    return result
