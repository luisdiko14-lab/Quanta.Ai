import hashlib

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis import redis_client


async def enforce_rate_limit(request: Request) -> None:
    """Apply a fixed-window per-IP limit. Redis failure is fail-closed."""
    remote = request.client.host if request.client else "unknown"
    fingerprint = hashlib.sha256(remote.encode("utf-8")).hexdigest()[:24]
    key = f"quanta:rate:{fingerprint}"

    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, settings.rate_limit_window_seconds)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request protection is temporarily unavailable. Please retry shortly.",
        ) from exc

    if count > settings.rate_limit_requests:
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit reached. Please wait before trying again.",
            headers={"Retry-After": str(max(ttl, 1))},
        )
