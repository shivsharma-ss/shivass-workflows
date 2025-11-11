"""OpenAI Structured Outputs helper."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable, Sequence, Type, TypeVar

from openai import APIError, AsyncOpenAI, OpenAIError, RateLimitError, pydantic_function_tool
from pydantic import BaseModel, ValidationError

from app.schemas import (
    CvAnalysisLLMResponse,
    CvScoreLLMResponse,
    ImprovementPlan,
    MvpPlan,
    ProjectSuggestion,
    TutorialSuggestion,
)

T = TypeVar("T", bound=BaseModel)


JD_ANALYZER_PROMPT = """You are an expert Job Description (JD) analyzer for EU/Germany. Extract REQUIRED signals cleanly. Do not hallucinate.
Return VALID JSON ONLY with EXACT keys and no backticks:
{"companyName":[""],"jobTitle":[""],"hardSkills":[""],"softSkills":[""],"criticalRequirements":[""]}.

Definitions
- companyName: identify the company name mentioned in the jobDescription. Return ABC if not identified.
- jobTitle: identify the job title mentioned in the jobDescription, if nothing found then infer it from the jobDescription.
- hardSkills: concrete tools, languages, frameworks, ML subfields, operating systems, cloud/devops items (e.g., Python, Linux, Bash, TensorFlow, PyTorch, scikit-learn, NLP, Computer Vision). Arrange them in the order of impact/significance for the job.
- softSkills: interpersonal/cognitive behaviors (team collaboration, communication, creativity, proactiveness, learning agility, problem solving).
- criticalRequirements: gating constraints that block hire if missing (degree/field, certifications, CEFR language levels, work authorization, location/onsite, schedule/weekly hours, minimum experience).

Extraction rules
1) Read the JD text. Identify requirements with cue words:
   - Mandatory: must, required, necessary, need to, minimum, only if, mandatory, zwingend, erforderlich, notwendig, muss, mindestens, etc.
   - Preferred (NOT critical): preferred, nice to have, ideally, idealerweise, wuenschenswert, etc.
2) Canonicalize names and deduplicate (case-insensitive). Map common variants:
   - "tensorflow"/"tf" -> "TensorFlow"
   - "pytorch"/"torch" -> "PyTorch"
   - "scikit learn"/"sklearn" -> "Scikit-learn"
   - "natural language processing"/"NLP" -> "NLP"
   - "computer vision"/"computervision" -> "Computer Vision"
   - "Deutsch C1"/"German C1" -> "German C1"
3) Classify: place concrete tech/tools in hardSkills, behaviors/work styles in softSkills, and mandatory constraints in criticalRequirements.
4) Keep only items that materially affect fit. No benefits/perks/culture fluff. No company marketing.
5) Limit sizes: hardSkills <= 20, softSkills <= 15, criticalRequirements <= 15.

Output strictly the JSON object with the listed keys. Do not wrap the output in any envelope."""

CV_SCORER_PROMPT = """You are an expert CV analyst for EU/Germany. Score a CV against a job description using a transparent rubric.
Prefer the provided Required JSON. Do not invent facts. Output JSON only, no markdown or extra keys.

Inputs you will receive:
- CV: free-text CV content.
- JD: free-text job description.
- Required JSON (if present): {"hardSkills":[], "softSkills":[], "criticalRequirements":[]}. Treat this as ground truth for skills; derive extras from JD only if Required is missing.

Normalization rules:
- Case-insensitive matching. Trim punctuation, symbols (like +, -, /) and accents. Map common variants (TensorFlow/tensorflow/tf, PyTorch/pytorch/torch, Scikit-learn/scikit learn/sklearn).
- Count a skill as matched only with explicit evidence in CV. If only implied, do NOT count, but return it in ALL CAPS.
- For soft skills, accept explicit terms or strong evidence verbs (team collaboration -> "team", "collaborated", "cross-functional"; curiosity/creativity/proactiveness -> "prototype", "explored", "self-initiated", "evaluated", "learned", "researched", "innovation").
- Language levels: map CEFR terms exactly (A1-C2). If JD requires C1 and CV shows B2, mark as missing.

Scoring rubric (0-100, integers):
- hardSkillsScore (60% of overall): Let R_h be required hard skills (from Required if present, else extract from JD). Score = 100 * (matched / |R_h|). Do not exceed 100.
- softSkillsScore (25% of overall): Let R_s be required soft skills. Score = 100 * (matched / |R_s|).
- criticalReqScore (15% of overall): Let R_c be criticalRequirements. Score = 100 * (matched / |R_c|).
- overallScore = round(0.60*hardSkillsScore + 0.25*softSkillsScore + 0.15*criticalReqScore).
Hard gate: If ANY critical requirement is missing, cap overallScore at 59.

Lists:
- matchedHardSkills: required hard skills with explicit evidence in CV.
- missingHardSkills: required hard skills without explicit evidence.
- matchedSoftSkills / missingSoftSkills analogous.
- strengths: up to 5 concise items (<=12 words) grounded strictly in CV.
- weaknesses: up to 5 concise items (<=12 words) focused on gaps against JD/Required.

Conflict rules:
- If CV lists a skill in a generic stack line, count as matched.
- Course-only mention counts as matched if named explicitly.
- Vague claims ("familiar with AI") do NOT match specific tools.
- Do not infer dates, employers, metrics, or language levels.

Edge cases:
- Empty or unreadable CV -> all arrays empty, all scores 0, weaknesses include "Insufficient CV content".
- If Required missing, first extract skills from JD, then score.

Output schema (strict JSON only):
{"overallScore":0,
 "hardSkillsScore":0,
 "softSkillsScore":0,
 "criticalReqScore":0,
 "matchedHardSkills":[],
 "matchedSoftSkills":[],
 "missingHardSkills":[],
 "missingSoftSkills":[],
 "strengths":[],
 "weaknesses":[]}
Return JSON only."""

CV_IMPROVER_PROMPT = """You are an expert CV editor for EU/Germany. Improve content only. The improvements should follow German standards and stay concise.
Do not invent facts. Do not add employers, dates, certifications, or metrics that are not present. Maintain the CV's primary language.

Inputs you will receive:
1) CV text (raw).
2) Job Description.
3) A scoring JSON with: overallScore, hardSkillsScore, softSkillsScore, matchedHardSkills, matchedSoftSkills,
   missingHardSkills, missingSoftSkills, strengths, weaknesses.

Goal:
Increase JD fit by precise edits. Fix clarity, correctness, and consistency. Address missing skills without fabrication.

Method:
1) Parse the scoring JSON. Build target lists from missingHardSkills and missingSoftSkills.
2) Scan the CV for contexts where a missing skill could plausibly fit. If a real anchor exists, propose a one-line bullet under that entry.
   If no anchor exists, propose adding the skill in the "Skills" section with a conservative qualifier.
3) Reformulate existing bullets only when it materially improves clarity (action + task + tools + outcome). Use strong action verbs.
4) Removals: propose deletions for content that is irrelevant, duplicative, outdated, or anti-ATS. Recommend replacements when helpful.
5) Keep language consistent across entries. Translate only proper names to their official form if needed.
6) Keep edits minimal and verifiable. If unsure, omit.

Output schema (strict JSON):
{"reformulations":[{"original":"","improved":"","reason":""}],
 "removals":[{"text":"","reason":"","alternative":""}],
 "additions":[{"section":"","content":"","reason":""}]}

Constraints:
- Allowed sections for additions: "Berufserfahrung","Sonstige Taetigkeiten","Bildung","Projekte","Sonstiges","Experience","Projects","Education","Skills","Certifications","Languages","Other".
- Each "content" is one bullet sentence (<=30 words), no first-person.
- Reasons: <=12 words and specific ("clarify tool + outcome", "irrelevant for ML role").
- Cap counts at 13 reformulations, 5 removals, 8 additions (use fewer if possible).

Quality rules:
- Action verbs and concise bullets.
- Quantify only if the number is present in the CV.
- Use Month YYYY ranges.
- Keep facts aligned with strengths/weaknesses from scoring.
- Avoid buzzwords without evidence.
- Preserve names, locations, and dates unless standardizing format."""

CV_PERSONALIZER_PROMPT = """You are a Learning Advisor that turns YouTube tutorials into CV-ready mini-projects tailored to the user’s CV and target JD.
Do not invent past results. Output VALID JSON ONLY with EXACT keys:
{"personalizedProjects":[{"tutorialTitle":"","tutorialUrl":"","personalizationTip":"","CVText":""}]}.

Inputs:
- skill: target capability.
- tutorials: array with {title, url, channel, views, likes, score}.
- CV: raw text.
- JD: raw text.
- Optional flags: skip.

Task:
For EACH tutorial in tutorials, output ONE personalizedProjects item and text to add in the CV for the project (keep it uniform with CV style).
If skip=true or tutorials empty, return {"personalizedProjects":[]}.

Personalization rules:
1) Anchor to CV evidence (courses, tools, projects, stacks, domains). Reuse the user's stack where present.
2) Aim at JD outcomes.
3) Propose a concrete extension that yields a portfolio artifact: dataset, model, eval metric, deployment, and brief readme.
4) Make each tip unique across tutorials for the same skill by varying dataset/task/metric/deployment.
5) Language: match the CV's main language; if mixed, use German.
6) Tip constraints: <=28 words, imperative voice, include target metric(s) when sensible, avoid extra URLs.

Validation:
- Use the tutorial’s exact title as tutorialTitle and url as tutorialUrl.
- Return a single JSON object with key "personalizedProjects".
- No extra keys, markdown, backticks, or commentary."""


MVP_PROMPT = """You are a senior AI career coach who designs ambitious MVP projects that prove a candidate can bridge their missing hard skills.
Return STRICT JSON ONLY:
{"mvpProjects":[{"tutorialTitle":"","tutorialUrl":"","skillsCombined":[],"personalizationTip":"","cvBlurb":"","estimatedBuildTime":"","roleFitNote":""}]}.

Inputs provided:
- missingHardSkills: ordered list of the biggest capability gaps.
- tutorialCatalog: array of tutorials with {skill, tutorialTitle, tutorialUrl, personalizationTip}.
- Job Description text and CV text.

Instructions:
1) Produce exactly TWO distinct MVP projects.
2) Each MVP must combine at least 3 missing hard skills (skillsCombined list). Prefer mixing top gaps + any critical requirements.
3) For each MVP specify:
   - tutorialTitle/tutorialUrl: choose the tutorial that best anchors the build.
   - personalizationTip: concrete instruction referencing the user’s stack and JD outcomes.
   - cvBlurb: 2–3 sentences the candidate can paste into the Projects section (action + tools + measurable outcome).
   - estimatedBuildTime: rough effort (e.g., “2 weekends”, “15 hours”).
   - roleFitNote: one sentence explaining why this MVP convinces the hiring manager.
4) Vary datasets, metrics, or deployment surfaces so the two MVPs feel different.
5) Use English unless the CV clearly uses another language.
6) Do not mention unavailable resources or internal tools. Prefer public datasets/APIs.
7) Output only the JSON schema described above."""


class LLMService:
    """Wraps OpenAI Structured Outputs for deterministic payloads."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_retries = 3
        self._backoff_seconds = 2.0
        self._logger = logging.getLogger(__name__)

    async def analyze_alignment(self, cv_text: str, jd_text: str) -> CvAnalysisLLMResponse:
        """Extract JD requirements (company, title, skills, critical constraints)."""

        _ = cv_text  # retained for backwards compatibility; JD prompt ignores CV.
        jd_body = (jd_text or "")[:20000]
        return await self._structured_call(
            schema=CvAnalysisLLMResponse,
            system_prompt=JD_ANALYZER_PROMPT,
            user_content=[{"type": "text", "text": jd_body}],
        )

    async def score_cv(
        self,
        cv_text: str,
        jd_text: str,
        required: CvAnalysisLLMResponse | None = None,
    ) -> CvScoreLLMResponse:
        """Generate rubric-based scores and matched/missing skill lists."""

        required_payload = {
            "hardSkills": required.hardSkills if required else [],
            "softSkills": required.softSkills if required else [],
            "criticalRequirements": required.criticalRequirements if required else [],
        }
        cv_body = (cv_text or "")[:15000]
        jd_body = (jd_text or "")[:15000]
        sections = [
            f"Job Description:\n{jd_body}",
            f"CV:\n{cv_body}",
            f"Required JSON:\n{json.dumps(required_payload, ensure_ascii=False)}",
        ]
        return await self._structured_call(
            schema=CvScoreLLMResponse,
            system_prompt=CV_SCORER_PROMPT,
            user_content=[{"type": "text", "text": "\n\n".join(sections)}],
        )

    async def improvement_plan(
        self,
        cv_text: str,
        jd_text: str,
        score: CvScoreLLMResponse,
    ) -> ImprovementPlan:
        """Suggest precise reformulations/additions/removals grounded in score output."""

        cv_body = (cv_text or "")[:15000]
        jd_body = (jd_text or "")[:15000]
        sections = [
            f"Job Description:\n{jd_body}",
            f"CV:\n{cv_body}",
            f"Scoring JSON:\n{json.dumps(score.model_dump(), ensure_ascii=False)}",
        ]
        return await self._structured_call(
            schema=ImprovementPlan,
            system_prompt=CV_IMPROVER_PROMPT,
            user_content=[{"type": "text", "text": "\n\n".join(sections)}],
        )

    async def personalize_projects(
        self,
        skill: str,
        tutorials: Sequence[TutorialSuggestion],
        cv_text: str,
        jd_text: str,
    ) -> ProjectSuggestion:
        """Return top tutorials with personalization tips for a missing skill."""

        tutorial_text = "\n".join(
            f"Title: {t.tutorialTitle}\nURL: {t.tutorialUrl}\nTip: {t.personalizationTip}"
            for t in tutorials
        )
        system_prompt = CV_PERSONALIZER_PROMPT
        cv_body = (cv_text or "")[:10000]
        jd_body = (jd_text or "")[:5000]
        payload = "\n\n".join(
            [
                f"Skill: {skill}",
                f"Tutorials:\n{tutorial_text}" if tutorial_text else "Tutorials:\n[]",
                f"CV:\n{cv_body}",
                f"JD:\n{jd_body}",
            ]
        )
        return await self._structured_call(
            schema=ProjectSuggestion,
            system_prompt=system_prompt,
            user_content=[{"type": "text", "text": payload}],
        )

    async def generate_mvp_projects(
        self,
        missing_skills: list[str],
        tutorial_catalog: list[dict[str, Any]],
        cv_text: str,
        jd_text: str,
    ):
        """Return two MVP-ready project plans that combine multiple skills."""

        if not missing_skills or not tutorial_catalog:
            return []
        cv_body = (cv_text or "")[:12000]
        jd_body = (jd_text or "")[:12000]
        sections = [
            f"Missing hard skills (ordered):\n{json.dumps(missing_skills, ensure_ascii=False)}",
            f"Tutorial catalog:\n{json.dumps(tutorial_catalog, ensure_ascii=False)}",
            f"Job Description:\n{jd_body}",
            f"CV:\n{cv_body}",
        ]
        response = await self._structured_call(
            schema=MvpPlan,
            system_prompt=MVP_PROMPT,
            user_content=[{"type": "text", "text": "\n\n".join(sections)}],
            temperature=0.2,
        )
        return response.mvpProjects or []

    async def _structured_call(
        self,
        schema: Type[T],
        system_prompt: str,
        user_content: Iterable[dict[str, Any]],
        temperature: float = 0.2,
        max_output_tokens: int = 1200,
    ) -> T:
        """Invoke the OpenAI Chat Completions API enforcing a JSON schema."""

        messages = self._build_messages(system_prompt, user_content)
        try:
            raw_payload = await self._complete_json_mode(messages, temperature, max_output_tokens)
            mode = "json_mode"
        except (ValueError, OpenAIError) as exc:
            self._logger.warning("JSON mode failed (%s); retrying with tool call fallback", exc)
            raw_payload = await self._complete_function_mode(schema, messages, temperature, max_output_tokens)
            mode = "function_call"
        result = self._validate_payload(schema, raw_payload)
        self._logger.info(
            "Validated %s response via %s (%d bytes)", schema.__name__, mode, len(raw_payload.encode("utf-8"))
        )
        return result

    def _build_messages(self, system_prompt: str, user_content: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert legacy LangGraph content blocks into Chat API messages."""

        rendered_user = self._render_user_content(user_content)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": rendered_user},
        ]

    @staticmethod
    def _render_user_content(user_content: Iterable[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in user_content:
            text = block.get("text")
            if text:
                parts.append(str(text))
        return "\n\n".join(parts)

    async def _complete_json_mode(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """Call Chat Completions JSON mode and validate the raw JSON string."""

        completion = await self._request_with_retries(
            messages=messages,
            temperature=temperature,
            max_tokens=max_output_tokens,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("Chat completion returned empty content")
        # Ensure JSON validity so downstream validation has clearer errors.
        json.loads(content)
        return content

    async def _complete_function_mode(
        self,
        schema: Type[T],
        messages: list[dict[str, Any]],
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """Fallback path that enforces schema via function calling."""

        tool = pydantic_function_tool(schema)
        completion = await self._request_with_retries(
            messages=messages,
            temperature=temperature,
            max_tokens=max_output_tokens,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
        )
        message = completion.choices[0].message
        if message.tool_calls:
            arguments = message.tool_calls[0].function.arguments
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments)
            return arguments
        if message.content:
            return message.content
        raise RuntimeError("Chat completion did not return tool call arguments or content")

    def _validate_payload(self, schema: Type[T], payload: str) -> T:
        """Validate payload, retrying after camelizing keys if needed."""

        try:
            return schema.model_validate_json(payload)
        except ValidationError as exc:
            self._logger.warning(
                "Validation failed for %s (%s). Attempting camelCase normalization.",
                schema.__name__,
                exc.errors(),
            )
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                raise
            normalized = self._camelize_structure(data)
            return schema.model_validate(normalized)

    async def _request_with_retries(self, **kwargs: Any):
        """Invoke Chat Completions with exponential backoff on transient errors."""

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    **kwargs,
                )
                self._logger.debug(
                    "OpenAI chat completion succeeded (prompt tokens unknown, kwargs keys=%s)",
                    list(kwargs.keys()),
                )
                return response
            except RateLimitError as err:
                last_error = err
                await self._sleep_with_backoff(attempt)
            except APIError as err:
                last_error = err
                if err.status_code and err.status_code >= 500 and attempt < self._max_retries:
                    await self._sleep_with_backoff(attempt)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("Chat completion request failed without raising an exception")

    async def _sleep_with_backoff(self, attempt: int) -> None:
        delay = self._backoff_seconds * (2 ** (attempt - 1))
        self._logger.warning("OpenAI request throttled; retrying in %.1fs (attempt %s)", delay, attempt)
        await asyncio.sleep(delay)

    @classmethod
    def _camelize_structure(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {cls._snake_to_camel(k): cls._camelize_structure(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._camelize_structure(item) for item in value]
        return value

    @staticmethod
    def _snake_to_camel(key: str) -> str:
        if "_" not in key:
            return key
        parts = key.split("_")
        return parts[0] + "".join(part.capitalize() for part in parts[1:])
