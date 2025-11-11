from __future__ import annotations

import json

from app.schemas import CvScoreLLMResponse
from services.llm import LLMService


def test_cv_score_model_accepts_snake_case_payload():
    payload = {
        "overall_score": 72,
        "hard_skills_score": 68,
        "soft_skills_score": 75,
        "critical_req_score": 50,
        "matched_hard_skills": ["Python"],
        "matched_soft_skills": ["Teamwork"],
        "missing_hard_skills": ["Go", "PostgreSQL"],
        "missing_soft_skills": ["Stakeholder communication"],
        "strengths": ["Python automation experience"],
        "weaknesses": ["No Go evidence"],
    }

    result = CvScoreLLMResponse.model_validate(payload)

    assert result.overallScore == 72
    assert result.missingHardSkills == ["Go", "PostgreSQL"]


def test_llm_service_camelize_structure_nested():
    data = {
        "missing_soft_skills": [{"skill_gap": "Storytelling"}],
        "nested_metric": {"overall_score": 80, "details": {"hard_skills_score": 70}},
    }

    normalized = LLMService._camelize_structure(data)

    assert normalized["missingSoftSkills"][0]["skillGap"] == "Storytelling"
    assert normalized["nestedMetric"]["overallScore"] == 80
    assert normalized["nestedMetric"]["details"]["hardSkillsScore"] == 70


def test_llm_service_validate_payload_normalizes_snake_case():
    service = LLMService(api_key="test-key", model="dummy-model")
    payload = json.dumps(
        {
            "overall_score": 60,
            "hard_skills_score": 55,
            "soft_skills_score": 70,
            "critical_req_score": 40,
            "matched_hard_skills": [],
            "matched_soft_skills": [],
            "missing_hard_skills": ["AWS"],
            "missing_soft_skills": [],
            "strengths": [],
            "weaknesses": ["Add AWS cert"],
        }
    )

    result = service._validate_payload(CvScoreLLMResponse, payload)

    assert result.overallScore == 60
    assert result.missingHardSkills == ["AWS"]
    assert result.weaknesses == ["Add AWS cert"]
