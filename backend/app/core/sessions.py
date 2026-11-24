import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.redis import redis_client

SESSION_COOKIE = "quanta_session"
CSRF_COOKIE = "quanta_csrf"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
PREAUTH_TTL_SECONDS = 60 * 15


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_key(token: str) -> str:
    return f"quanta:session:{_digest(token)}"


def _secure_cookie() -> bool:
    return settings.app_env.lower() == "production"


async def load_session(request: Request) -> tuple[str, dict[str, Any]] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    raw = await redis_client.get(_session_key(token))
    if not raw:
        return None
    try:
        return token, json.loads(raw)
    except json.JSONDecodeError:
        await redis_client.delete(_session_key(token))
        return None


async def create_session(response: Response, identity: dict[str, Any]) -> str:
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    payload = {**identity, "csrf_hash": _digest(csrf_token)}
    await redis_client.set(
        _session_key(session_token),
        json.dumps(payload, separators=(",", ":")),
        ex=SESSION_TTL_SECONDS,
    )
    if identity.get("user_id"):
        user_sessions = f"quanta:user-sessions:{identity['user_id']}"
        await redis_client.sadd(user_sessions, _digest(session_token))
        await redis_client.expire(user_sessions, SESSION_TTL_SECONDS)
    response.set_cookie(
        SESSION_COOKIE, session_token, max_age=SESSION_TTL_SECONDS,
        httponly=True, secure=_secure_cookie(), samesite="strict", path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=SESSION_TTL_SECONDS,
        httponly=False, secure=_secure_cookie(), samesite="strict", path="/",
    )
    return csrf_token


async def issue_csrf_token(request: Request, response: Response) -> str:
    session = await load_session(request)
    csrf_token = request.cookies.get(CSRF_COOKIE)
    if session and csrf_token:
        _, payload = session
        if hmac.compare_digest(payload.get("csrf_hash", ""), _digest(csrf_token)):
            return csrf_token

    csrf_token = secrets.token_urlsafe(32)
    if session:
        session_token, payload = session
        payload["csrf_hash"] = _digest(csrf_token)
        await redis_client.set(
            _session_key(session_token),
            json.dumps(payload, separators=(",", ":")),
            ex=SESSION_TTL_SECONDS,
        )
        max_age = SESSION_TTL_SECONDS
    else:
        await redis_client.set(
            f"quanta:preauth:{_digest(csrf_token)}", "1", ex=PREAUTH_TTL_SECONDS
        )
        max_age = PREAUTH_TTL_SECONDS

    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False,
        secure=_secure_cookie(), samesite="strict", path="/",
    )
    return csrf_token


async def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if not cookie_token or not header_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required.")
    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")

    session = await load_session(request)
    if session:
        _, payload = session
        if hmac.compare_digest(payload.get("csrf_hash", ""), _digest(cookie_token)):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")

    exists = await redis_client.exists(f"quanta:preauth:{_digest(cookie_token)}")
    if not exists:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token expired.")


async def require_identity(request: Request) -> dict[str, Any]:
    session = await load_session(request)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid guest or user session is required.",
        )
    return session[1]


async def destroy_session(request: Request, response: Response) -> None:
    session = await load_session(request)
    if session:
        token, identity = session
        await redis_client.delete(_session_key(token))
        if identity.get("user_id"):
            user_sessions = f"quanta:user-sessions:{identity['user_id']}"
            await redis_client.srem(user_sessions, _digest(token))
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=_secure_cookie(), httponly=True, samesite="strict"
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=_secure_cookie(), httponly=False, samesite="strict"
    )



async def revoke_user_sessions(user_id: str) -> None:
    """Revoke all Redis sessions associated with a user."""
    user_sessions = f"quanta:user-sessions:{user_id}"
    session_digests = await redis_client.smembers(user_sessions)
    if session_digests:
        keys = [f"quanta:session:{digest}" for digest in session_digests]
        await redis_client.delete(*keys)
    await redis_client.delete(user_sessions)
