"""Helpers for managing Google OAuth authorization flows."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"


from functools import partialmethod
from urllib.parse import urlencode


class GoogleOAuthService:
    """Generates consent URLs and exchanges authorization codes for tokens."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_uri: str,
        scopes: list[str],
    ) -> None:
        if not client_id or not client_secret or not redirect_uri:
            raise ValueError("Google OAuth client is not fully configured")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_uri = token_uri
        self._scopes = scopes

    def _client_config(self) -> dict[str, Any]:
        return {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": GOOGLE_AUTH_URI,
                "token_uri": self._token_uri,
                "redirect_uris": [self._redirect_uri],
            }
        }

    def _build_flow(self, state: Optional[str] = None) -> Flow:
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self._scopes,
            state=state,
        )
        # Configure the flow to be lenient about scope ordering
        flow.oauth2session.scope_change_wizardry = True
        return flow

    def generate_authorize_url(self) -> tuple[str, str]:
        """Return the Google consent screen URL plus opaque state string."""

        flow = self._build_flow()
        flow.redirect_uri = self._redirect_uri
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return authorization_url, state

    async def exchange_code(self, code: str, state: Optional[str] = None) -> tuple[dict[str, Any], str]:
        """Swap an authorization code for refreshable credentials."""

        flow = self._build_flow(state)
        flow.redirect_uri = self._redirect_uri
        credentials = await asyncio.to_thread(self._fetch_token, flow, code)
        email = await self._resolve_email(credentials)
        payload = self._serialize_credentials(credentials)
        if not email:
            raise RuntimeError("Unable to determine Google account email from OAuth response")
        return payload, email

    def _fetch_token(self, flow: Flow, code: str):
        try:
            # Manually construct token fetch parameters
            token_params = {
                'client_id': self._client_id,
                'client_secret': self._client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': self._redirect_uri
            }
            
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            async def _fetch():
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        self._token_uri,
                        data=token_params,
                        headers=headers
                    )
                    response.raise_for_status()
                    return response.json()

            # Run the token fetch in a thread since we're called in a thread already
            import asyncio
            loop = asyncio.new_event_loop()
            token_data = loop.run_until_complete(_fetch())
            loop.close()

            # Convert the token response to the expected format
            import time
            token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)
            
            # Create credentials from the token response
            flow.oauth2session.token = token_data
            return flow.credentials
        except Exception as e:
            raise RuntimeError(f"Failed to fetch token: {e}") from e

    async def _resolve_email(self, credentials) -> Optional[str]:
        if credentials.id_token:
            def _verify():
                return id_token.verify_oauth2_token(credentials.id_token, Request(), self._client_id)

            info = await asyncio.to_thread(_verify)
            email = info.get("email")
            if email:
                return email
        headers = {"Authorization": f"Bearer {credentials.token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(USERINFO_ENDPOINT, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("email")

    def _serialize_credentials(self, credentials) -> dict[str, Any]:
        expiry = credentials.expiry.isoformat() if credentials.expiry else None
        return {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": expiry,
        }
