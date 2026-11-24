from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.rate_limit import enforce_rate_limit
from app.schemas.chat import ChatRequest
from app.services.ai import complete_chat, public_models, provider_status, stream_chat

router = APIRouter(prefix="/api/v1", tags=["Quanta AI"])


@router.get("/models")
async def list_models() -> dict:
    return {"data": public_models()}


@router.get("/providers")
async def list_providers() -> dict:
    return {"data": provider_status()}


@router.post("/chat/completions", dependencies=[Depends(enforce_rate_limit)])
async def chat_completions(payload: ChatRequest):
    if payload.stream:
        return StreamingResponse(
            stream_chat(payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    return await complete_chat(payload)
