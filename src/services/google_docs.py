"""Google Docs update helpers."""
from __future__ import annotations

from typing import Optional

from googleapiclient.discovery import build

from services.google_service_account import ServiceAccountCredentialChain

DOCS_SCOPES = [
    "https://www.googleapis.com/auth/documents",
]


class GoogleDocsService:
    """Wrapper around Docs batchUpdate for InsertTextRequest at index 1."""

    def __init__(self, service_account_file: str, subject: Optional[str] = None) -> None:
        self._credential_chain = ServiceAccountCredentialChain(service_account_file, DOCS_SCOPES, subject)

    def prepend_text(self, doc_id: str, text: str) -> dict:
        """Insert text at the top of the document."""

        def _update(creds):
            docs = build("docs", "v1", credentials=creds)
            body = {
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": text,
                        }
                    }
                ]
            }
            return docs.documents().batchUpdate(documentId=doc_id, body=body).execute()

        return self._credential_chain.run(_update)
