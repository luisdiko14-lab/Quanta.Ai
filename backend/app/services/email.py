import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings


def _send_email(recipient: str, subject: str, body: str) -> None:
    sender = settings.smtp_from_email or settings.smtp_username
    if not settings.smtp_host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL must be configured.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        if settings.smtp_use_tls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


async def send_email(recipient: str, subject: str, body: str) -> None:
    await asyncio.to_thread(_send_email, recipient, subject, body)
