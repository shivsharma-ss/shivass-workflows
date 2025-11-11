"""Application configuration helpers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings sourced from environment variables."""

    app_env: str = Field(default="local", alias="APP_ENV")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    youtube_api_key: Optional[str] = Field(default=None, alias="YOUTUBE_API_KEY")
    google_service_account_file: Path = Field(alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    google_workspace_subject: Optional[str] = Field(default=None, alias="GOOGLE_WORKSPACE_SUBJECT")
    gmail_sender: EmailStr = Field(alias="GMAIL_SENDER")
    google_oauth_client_id: Optional[str] = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: Optional[str] = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: Optional[str] = Field(default=None, alias="GOOGLE_OAUTH_REDIRECT_URI")
    google_oauth_token_uri: str = Field(
        default="https://oauth2.googleapis.com/token",
        alias="GOOGLE_OAUTH_TOKEN_URI",
    )
    smtp_server: str = Field(alias="SMTP_SERVER")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, alias="SMTP_PASSWORD")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    database_url: str = Field(default="sqlite+aiosqlite:///./data/orchestrator.db", alias="DATABASE_URL")
    frontend_base_url: str = Field(default="http://localhost:8001", alias="FRONTEND_BASE_URL")
    review_secret: str = Field(alias="REVIEW_SECRET")
    youtube_quota_daily: int = Field(default=10000, alias="YOUTUBE_QUOTA_DAILY")
    email_smoke_recipient: Optional[EmailStr] = Field(default=None, alias="EMAIL_SMOKE_RECIPIENT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        frozen=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance to avoid repeated parsing."""
    return Settings()
