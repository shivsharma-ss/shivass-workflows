"""Google Drive helpers."""
from __future__ import annotations

from typing import Optional

from googleapiclient.discovery import build

from services.google_service_account import ServiceAccountCredentialChain

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleDriveService:
    """Exports Google Docs as plain text via Drive files.export."""

    def __init__(self, service_account_file: str, subject: Optional[str] = None) -> None:
        self._credential_chain = ServiceAccountCredentialChain(service_account_file, DRIVE_SCOPES, subject)

    def export_doc_text(self, doc_id: str) -> str:
        """Return the raw text of a Google Doc."""

        def _export(creds):
            drive = build("drive", "v3", credentials=creds)
            request = drive.files().export(fileId=doc_id, mimeType="text/plain")
            data = request.execute()
            if isinstance(data, bytes):
                return data.decode("utf-8")
            return str(data)

        return self._credential_chain.run(_export)
