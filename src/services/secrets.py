"""Lightweight secrets abstraction."""
from __future__ import annotations

import os
from typing import Optional


class SecretsService:
    """Fetch secrets from the environment."""

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return a secret value by key."""

        return os.environ.get(key, default)
