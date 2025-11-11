"""Shared helpers for Google service-account credential flows."""
from __future__ import annotations

import logging
from typing import Callable, Iterable, Optional, TypeVar

from google.auth.exceptions import RefreshError
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceAccountCredentialChain:
    """Wraps service-account credentials with optional domain-wide delegation fallback."""

    def __init__(self, service_account_file: str, scopes: list[str], subject: Optional[str]) -> None:
        base_creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        subject = subject or None
        delegated = base_creds.with_subject(subject) if subject else None

        self._base_creds = base_creds
        self._delegated_creds = delegated
        self._subject = subject

    def _credential_order(self) -> Iterable[Credentials]:
        if self._delegated_creds is not None:
            yield self._delegated_creds
        yield self._base_creds

    def run(self, fn: Callable[[Credentials], T]) -> T:
        """Execute `fn` with each credential option, falling back on RefreshError."""

        last_refresh_error: Optional[RefreshError] = None
        for creds in self._credential_order():
            try:
                return fn(creds)
            except RefreshError as exc:
                if self._delegated_creds is None or creds is self._base_creds:
                    # No fallback remains, bubble up the refresh failure.
                    raise
                last_refresh_error = exc
                logger.warning(
                    "Unable to impersonate %s via service account %s (%s); "
                    "retrying without domain delegation.",
                    self._subject,
                    self._base_creds.service_account_email,
                    exc,
                )
        if last_refresh_error is not None:
            raise last_refresh_error
        raise RuntimeError("ServiceAccountCredentialChain had no credentials to execute with")

