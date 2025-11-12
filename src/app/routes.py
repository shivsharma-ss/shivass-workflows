"""FastAPI routes for the orchestrator."""
from __future__ import annotations

from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings
from app.schemas import (
    AnalysisArtifact,
    AnalysisListResponse,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisSummary,
    AnalysisStatus,
    AnalysisStatusResponse,
    ApprovalRequest,
)
from services.container import AppContainer

router = APIRouter()
OAUTH_STATE_KEY = "oauth-state:"
logger = logging.getLogger(__name__)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[attr-defined]


@router.post("/v1/analyses", response_model=AnalysisResponse)
async def create_analysis(
    payload: AnalysisRequest,
    container: AppContainer = Depends(get_container),
) -> AnalysisResponse:
    analysis_id, status = await container.runner.kickoff(payload)
    return AnalysisResponse(analysisId=analysis_id, status=status)


@router.get("/v1/analyses", response_model=AnalysisListResponse)
async def list_analyses(
    limit: int = Query(50, ge=1, le=100),
    status: AnalysisStatus | None = Query(None),
    container: AppContainer = Depends(get_container),
) -> AnalysisListResponse:
    records = await container.storage.list_analyses(limit=limit, status=status)
    items = [
        AnalysisSummary(
            analysisId=record.analysis_id,
            email=record.email,
            cvDocId=record.cv_doc_id,
            status=record.status,
            lastError=record.last_error,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
        )
        for record in records
    ]
    return AnalysisListResponse(items=items)


@router.get("/v1/analyses/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis(
    analysis_id: str,
    container: AppContainer = Depends(get_container),
) -> AnalysisStatusResponse:
    record = await container.storage.get_analysis(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisStatusResponse(
        analysisId=record.analysis_id,
        status=record.status,
        lastError=record.last_error,
        payload=record.payload,
    )


@router.get("/v1/analyses/{analysis_id}/artifacts", response_model=list[AnalysisArtifact])
async def list_analysis_artifacts(
    analysis_id: str,
    container: AppContainer = Depends(get_container),
) -> list[AnalysisArtifact]:
    record = await container.storage.get_analysis(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    raw_artifacts = await container.storage.list_artifacts(analysis_id)
    artifacts: list[AnalysisArtifact] = []
    for item in raw_artifacts:
        try:
            created_at_value = item["created_at"]
        except KeyError as exc:
            logger.error(
                "Missing created_at for artifact %s of analysis %s",
                item.get("artifact_type"),
                analysis_id,
                exc_info=exc,
            )
            raise HTTPException(
                status_code=400, detail="Artifact created_at timestamp is missing or invalid"
            ) from exc
        try:
            created_at = datetime.fromisoformat(created_at_value)
        except ValueError as exc:
            logger.error(
                "Invalid created_at %r for artifact %s of analysis %s",
                created_at_value,
                item.get("artifact_type"),
                analysis_id,
                exc_info=exc,
            )
            raise HTTPException(
                status_code=400, detail="Artifact created_at timestamp is missing or invalid"
            ) from exc
        artifacts.append(
            AnalysisArtifact(
                analysisId=analysis_id,
                artifactType=item["artifact_type"],
                content=item["content"],
                createdAt=created_at,
            )
        )
    return artifacts


@router.post("/review/approve", response_model=AnalysisResponse)
async def approve(
    payload: ApprovalRequest,
    container: AppContainer = Depends(get_container),
) -> AnalysisResponse:
    serializer = URLSafeSerializer(get_settings().review_secret, salt="approval")
    try:
        data = serializer.loads(payload.token)
    except BadSignature as exc:  # pragma: no cover - cryptographic guard
        raise HTTPException(status_code=400, detail="Invalid token") from exc
    if data.get("analysis_id") != payload.analysisId:
        raise HTTPException(status_code=400, detail="Token mismatch")
    record = await container.storage.get_analysis(payload.analysisId)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if record.status != AnalysisStatus.AWAITING_APPROVAL:
        return AnalysisResponse(analysisId=payload.analysisId, status=record.status)
    status = await container.runner.resume(payload.analysisId)
    return AnalysisResponse(analysisId=payload.analysisId, status=status)


@router.get("/oauth/google/start", include_in_schema=False)
async def google_oauth_start(container: AppContainer = Depends(get_container)) -> RedirectResponse:
    if not container.google_oauth:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    url, state = container.google_oauth.generate_authorize_url()
    await container.cache.set(f"{OAUTH_STATE_KEY}{state}", {"state": state}, ttl_seconds=600)
    return RedirectResponse(url)


@router.get("/oauth/google/callback", include_in_schema=False)
async def google_oauth_callback(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> HTMLResponse:
    if not container.google_oauth:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    params = request.query_params
    if "error" in params:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {params['error']}")
    code = params.get("code")
    state = params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    cached = await container.cache.get(f"{OAUTH_STATE_KEY}{state}")
    if not cached:
        raise HTTPException(status_code=400, detail="Unknown or expired state")
    credentials, email = await container.google_oauth.exchange_code(code, state=state)
    expected_sender = container.settings.gmail_sender.lower()
    if email.lower() != expected_sender:
        raise HTTPException(
            status_code=400,
            detail=f"Authorized Google account {email} does not match expected sender {container.settings.gmail_sender}",
        )
    await container.token_store.save("google", container.settings.gmail_sender, credentials)
    message = "<h3>Gmail authorization complete. You may close this window.</h3>"
    return HTMLResponse(message)
