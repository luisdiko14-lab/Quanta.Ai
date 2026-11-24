from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.auth import router as auth_router
from app.core.rate_limit import enforce_rate_limit
from app.core.sessions import require_csrf, require_identity
from app.schemas.chat import ChatRequest
from app.services.ai import complete_chat, provider_status, public_models, stream_chat

router = APIRouter(prefix="/api/v1", tags=["Quanta AI"])
router.include_router(auth_router)


@router.get("/models")
async def list_models() -> dict:
    return {"data": public_models()}


@router.get("/providers")
async def list_providers() -> dict:
    return {"data": provider_status()}


@router.post(
    "/chat/completions",
    dependencies=[Depends(enforce_rate_limit), Depends(require_csrf)],
)
async def chat_completions(
    payload: ChatRequest,
    identity: Annotated[dict, Depends(require_identity)],
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

    if payload.stream:
        return StreamingResponse(
            stream_chat(payload, allow_premium=premium_access),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    return await complete_chat(payload, allow_premium=premium_access)
