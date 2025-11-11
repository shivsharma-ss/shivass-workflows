"""Persistent OAuth token store backed by StorageService."""
from __future__ import annotations

from typing import Any, Optional

from services.storage import StorageService


class OAuthTokenStore:
    """Thin wrapper that persists OAuth credentials per provider/account."""

    def __init__(self, storage: StorageService):
        self._storage = storage

    async def save(self, provider: str, account: str, credentials: dict[str, Any]) -> None:
        """Persist credentials for later reuse."""

        await self._storage.save_oauth_credentials(provider, account, credentials)

    async def get(self, provider: str, account: str) -> Optional[dict[str, Any]]:
        """Return stored credentials for the provider/account, if any."""

        return await self._storage.get_oauth_credentials(provider, account)
