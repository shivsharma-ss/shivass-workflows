"""Application container wiring configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.config import Settings
from orchestrator.graph import build_graph
from orchestrator.runner import OrchestratorRunner
from orchestrator.state import NodeDeps
from services.cache import CacheService
from services.gmail import GmailService
from services.google_docs import GoogleDocsService
from services.google_drive import GoogleDriveService
from services.google_oauth import GoogleOAuthService
from services.gemini import GeminiService
from services.llm import LLMService
from services.oauth_tokens import OAuthTokenStore
from services.ranking import RankingService
from services.storage import StorageService
from services.youtube import YouTubeService


class AppContainer:
    """Simple service locator for FastAPI dependency injection."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache = CacheService(settings.redis_url)
        self.storage = StorageService(settings.database_url)
        self.token_store = OAuthTokenStore(self.storage)
        self.drive = GoogleDriveService(settings.google_service_account_file, settings.google_workspace_subject)
        self.docs = GoogleDocsService(settings.google_service_account_file, settings.google_workspace_subject)
        templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
        self.google_oauth: Optional[GoogleOAuthService] = None
        if (
            settings.google_oauth_client_id
            and settings.google_oauth_client_secret
            and settings.google_oauth_redirect_uri
        ):
            self.google_oauth = GoogleOAuthService(
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                redirect_uri=settings.google_oauth_redirect_uri,
                token_uri=settings.google_oauth_token_uri,
                scopes=[
                    "openid",
                    "email",
                    "profile",
                    "https://www.googleapis.com/auth/gmail.send",
                ],
            )
        self.gmail = GmailService(
            templates_path=str(templates_dir),
            sender=settings.gmail_sender,
            subject_override=None,
            oauth_token_store=self.token_store,
            smtp_server=settings.smtp_server or None,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
        )
        self.llm = LLMService(settings.openai_api_key)
        self.ranking = RankingService()
        self.youtube: Optional[YouTubeService] = None
        if settings.youtube_api_key:
            self.youtube = YouTubeService(
                api_key=settings.youtube_api_key,
                cache=self.cache,
                storage=self.storage,
                daily_quota=settings.youtube_quota_daily,
            )
        self.gemini: Optional[GeminiService] = None
        if settings.gemini_api_key:
            self.gemini = GeminiService(
                api_key=settings.gemini_api_key,
                cache=self.cache,
                storage=self.storage,
            )
        node_deps = NodeDeps(
            settings=settings,
            storage=self.storage,
            drive=self.drive,
            docs=self.docs,
            gmail=self.gmail,
            llm=self.llm,
            ranking=self.ranking,
            youtube=self.youtube,
            gemini=self.gemini,
        )
        self.graph = build_graph(node_deps)
        self.runner = OrchestratorRunner(self.graph, node_deps)

    async def startup(self) -> None:
        """Initialize resources like the database."""

        await self.storage.initialize()
