import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.redis import redis_client
from app.core.security import hash_password, verify_password
from app.core.sessions import (
    create_session,
    destroy_session,
    issue_csrf_token,
    require_csrf,
    require_identity,
)
from app.db.models import User
from app.db.session import get_db_session
from app.schemas.auth import LoginRequest, RegisterRequest, VerifyEmailRequest
from app.services.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/csrf")
async def csrf_token(request: Request, response: Response) -> dict[str, str]:
    token = await issue_csrf_token(request, response)
    return {"csrf_token": token}


@router.get("/me")
async def me(identity: dict = Depends(require_identity)) -> dict:
    return {
        "authenticated": True,
        "user_id": identity.get("user_id"),
        "username": identity.get("username"),
        "display_name": identity.get("display_name"),
        "role": identity.get("role"),
        "plan": identity.get("plan"),
        "kind": identity.get("kind"),
    }


@router.post("/guest", dependencies=[Depends(require_csrf), Depends(enforce_rate_limit)])
async def create_guest(response: Response) -> dict[str, str]:
    csrf = await create_session(
        response,
        {
            "user_id": None,
            "username": "Guest",
            "display_name": "Guest workspace",
            "role": "guest",
            "plan": "guest",
            "kind": "guest",
        },
    )
    return {"status": "ok", "csrf_token": csrf, "kind": "guest"}


@router.post("/register", dependencies=[Depends(require_csrf), Depends(enforce_rate_limit)])
async def register_account(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if settings.app_env.lower() == "production" and (
        not settings.smtp_host or not settings.smtp_from_email
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "Account registration is temporarily unavailable because email is not configured."
            ),
        )

    email = str(payload.email).lower()
    username = payload.username.lower()
    existing = await session.scalar(
        select(User).where(
            or_(func.lower(User.email) == email, func.lower(User.username) == username)
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="That email or username is already in use.")

    password_hash = await asyncio.to_thread(hash_password, payload.password)
    user = User(
        email=email,
        username=username,
        display_name=payload.display_name.strip() or username,
        password_hash=password_hash,
        role="user",
        plan="free",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="That email or username is already in use."
        ) from exc

    verification_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(verification_token.encode("utf-8")).hexdigest()
    await redis_client.set(
        f"quanta:verify-email:{token_hash}",
        str(user.id),
        ex=60 * 60 * 24,
    )
    verification_url = (
        f"{settings.frontend_base_url.rstrip('/')}/verify-email?token={verification_token}"
    )

    if settings.smtp_host and settings.smtp_from_email:
        try:
            await send_email(
                user.email,
                "Verify your Quanta AI email",
                "Welcome to Quanta AI. Verify your email using this link:\n\n"
                f"{verification_url}\n\nThis link expires in 24 hours.",
            )
        except Exception as exc:
            logger.exception("Failed to send email verification message.")
            raise HTTPException(
                status_code=503,
                detail="Your account was created, but the verification email could not be sent.",
            ) from exc
        return {
            "status": "pending_verification",
            "message": "Check your email to verify your account.",
        }

    return {
        "status": "pending_verification",
        "message": "Email is not configured. Use this development-only verification token.",
        "development_verification_token": verification_token,
    }


@router.post("/verify-email", dependencies=[Depends(require_csrf), Depends(enforce_rate_limit)])
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    redis_key = f"quanta:verify-email:{token_hash}"
    user_id = await redis_client.get(redis_key)
    if not user_id:
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired.")

    user = await session.get(User, UUID(user_id))
    if not user:
        await redis_client.delete(redis_key)
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired.")

    user.email_verified_at = datetime.now(timezone.utc)
    await session.commit()
    await redis_client.delete(redis_key)
    return {
        "status": "verified",
        "message": "Your email has been verified. You can now sign in.",
    }


@router.post("/login", dependencies=[Depends(require_csrf), Depends(enforce_rate_limit)])
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    login_value = payload.login.lower().strip()
    user = await session.scalar(
        select(User).where(
            or_(
                func.lower(User.email) == login_value,
                func.lower(User.username) == login_value,
            )
        )
    )
    password_valid = await asyncio.to_thread(
        verify_password,
        payload.password,
        user.password_hash if user else "",
    )
    if not user or not password_valid:
        raise HTTPException(status_code=401, detail="Incorrect username/email or password.")
    if not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Please verify your email before signing in.")

    csrf = await create_session(
        response,
        {
            "user_id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "plan": user.plan,
            "kind": "user",
        },
    )
    return {
        "status": "ok",
        "csrf_token": csrf,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "plan": user.plan,
        },
    }


@router.post("/logout", dependencies=[Depends(require_identity), Depends(require_csrf)])
async def logout(request: Request, response: Response) -> dict[str, str]:
    await destroy_session(request, response)
    return {"status": "ok"}
