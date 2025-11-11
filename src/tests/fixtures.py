"""Reusable test fixtures."""
from app.schemas import AnalysisRequest

SAMPLE_REQUEST = AnalysisRequest(
    email="sample@example.com",
    cvDocId="doc123",
    jobDescription="Sample JD",
    jobDescriptionUrl=None,
)
