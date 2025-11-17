"""Email sending via Gmail API with SMTP fallback."""
from __future__ import annotations

import asyncio
import base64
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader, select_autoescape

from services.oauth_tokens import OAuthTokenStore

EMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
OAUTH_PROVIDER = "google"
logger = logging.getLogger(__name__)


class GmailService:
    """Send rich HTML emails via Gmail using OAuth/service accounts with SMTP fallback."""

    def __init__(
        self,
        templates_path: str,
        sender: str,
        subject_override: Optional[str],
        oauth_token_store: Optional[OAuthTokenStore],
        service_account_file: Optional[str] = None,
        subject_user: Optional[str] = None,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> None:
        self._sender = sender
        self._subject_override = subject_override
        self._token_store = oauth_token_store
        self._service_account_file = service_account_file
        self._subject_user = subject_user
        self._smtp_server = (smtp_server or "").strip()
        self._smtp_port = smtp_port
        self._smtp_username = smtp_username
        self._smtp_password = smtp_password
        self._env = Environment(
            loader=FileSystemLoader(templates_path),
            autoescape=select_autoescape(["html", "j2"]),
        )
        self._service_account_creds = (
            service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=EMAIL_SCOPES,
                subject=subject_user,
            )
            if service_account_file
            else None
        )

    def render(self, template: str, **context) -> str:
        """Render an email template."""

        tpl = self._env.get_template(template)
        return tpl.render(**context)

    async def send_html(self, to_email: str, subject: str, html: str) -> dict[str, Any]:
        """Send HTML email using Gmail API; fall back to SMTP if needed."""

        message = self._build_message(to_email, subject, html)
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        gmail_result = await self._try_gmail_send(raw_message)
        if gmail_result:
            return gmail_result

        smtp_result = await self._try_smtp_send(message)
        if smtp_result:
            return smtp_result

        raise RuntimeError("Unable to send email: Gmail API unavailable and SMTP not configured")

    def _build_message(self, to_email: str, subject: str, html: str) -> MIMEMultipart:
        message = MIMEMultipart("alternative")
        message["Subject"] = self._subject_override or subject
        message["From"] = self._sender
        message["To"] = to_email
        message.attach(MIMEText(html, "html"))
        return message

    async def _try_gmail_send(self, raw_message: str) -> Optional[dict[str, Any]]:
        if not (self._token_store or self._service_account_creds):
            return None
        try:
            creds = await self._resolve_credentials()
        except Exception as exc:
            logger.error("Failed to load Gmail credentials; falling back to SMTP", exc_info=exc)
            return None
        if not creds:
            return None
        try:
            return await asyncio.to_thread(self._send_raw_message, creds, raw_message)
        except Exception as exc:
            logger.error("Gmail API send failed; falling back to SMTP", exc_info=exc)
            return None

    async def _try_smtp_send(self, message: MIMEMultipart) -> Optional[dict[str, Any]]:
        if not (self._smtp_server and self._smtp_username and self._smtp_password):
            return None
        return await asyncio.to_thread(self._send_via_smtp, message)

    def _send_raw_message(self, creds, raw_message: str) -> dict[str, Any]:
        gmail = build("gmail", "v1", credentials=creds)
        return (
            gmail.users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )

    def _send_via_smtp(self, message: MIMEMultipart) -> dict[str, Any]:
        with smtplib.SMTP(self._smtp_server, self._smtp_port, timeout=30) as server:
            server.starttls()
            server.login(self._smtp_username, self._smtp_password)
            server.sendmail(self._sender, [message["To"]], message.as_string())
        return {"transport": "smtp", "status": "sent"}

    async def _resolve_credentials(self):
        oauth_creds = await self._load_user_credentials()
        if oauth_creds:
            return oauth_creds
        if self._service_account_creds:
            return self._service_account_creds
        return None

    async def _load_user_credentials(self):
        if not self._token_store:
            return None
        token_data = await self._token_store.get(OAUTH_PROVIDER, self._sender)
        if not token_data:
            return None
        creds = user_credentials.Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )
        expiry = token_data.get("expiry")
        if expiry:
            parsed = datetime.fromisoformat(expiry)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            creds.expiry = parsed
        if creds.expired and creds.refresh_token:
            try:
                await asyncio.to_thread(creds.refresh, Request())
                token_data["token"] = creds.token
                token_data["expiry"] = creds.expiry.isoformat() if creds.expiry else None
                await self._token_store.save(OAUTH_PROVIDER, self._sender, token_data)
                logger.info("Refreshed Gmail OAuth token for %s", self._sender)
            except Exception as exc:
                logger.error("Failed refreshing Gmail OAuth token for %s", self._sender, exc_info=exc)
                raise
        return creds
