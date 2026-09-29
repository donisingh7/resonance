"""Real OpenAI-backed AIProvider adapter (P1.2).

Implements the same `AIProvider` interface as `MockAIProvider` — nothing
downstream (`processing.py`, `intelligence.py`, `questionnaire.py`) needs to
know which one is active. Selected via `AI_PROVIDER=openai`; `mock` remains
the default and requires none of this module's configuration.

Structured output (project synthesis, questionnaire generation) uses the
SDK's `responses.parse(..., text_format=<pydantic model>)` schema-based
parsing rather than free-form JSON parsing, so a malformed response raises
instead of producing corrupted/guessed content. The Pydantic schemas below
are internal to this module — the public `AIProvider` contract in
`base.py` (TypedDicts) is unchanged.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_providers.base import (
    AIProvider,
    GeneratedQuestion,
    ImageAnalysisResult,
    IntelligenceContext,
    ProjectAssetContext,
    ProjectSynthesisResult,
    QuestionnaireGenerationResult,
    TranscriptionResult,
)


class OpenAIConfigurationError(ValueError):
    """AI_PROVIDER=openai but required OpenAI settings are missing.

    Subclasses ValueError so the existing readiness check
    (`readiness._check_ai_provider_configured`, which already catches
    ValueError from `get_ai_provider()`) reports this cleanly with no
    changes needed there.
    """


class OpenAIProviderError(RuntimeError):
    """The OpenAI API returned output this adapter can't use.

    Never caught here to invent fallback content or silently switch to
    mock — callers (processing.py / intelligence.py / questionnaire.py)
    already catch provider exceptions and turn them into a status="failed"
    result, exactly as they do for MockAIProvider... except MockAIProvider
    never actually raises.
    """


# --- structured-output schemas (module-internal only) --------------------


class _EvidenceItemSchema(BaseModel):
    category: str
    statement: str
    asset_id: str
    processing_result_id: str
    source_filename: str
    excerpt: str | None = None


class _ProjectSynthesisSchema(BaseModel):
    summary: str
    top_themes: list[str]
    sentiment_summary: str
    pain_points: list[str]
    positive_signals: list[str]
    questions_or_concerns: list[str]
    opportunities: list[str]
    recommended_actions: list[str]
    evidence: list[_EvidenceItemSchema]


class _ImageAnalysisSchema(BaseModel):
    extracted_text: str | None
    visual_description: str


class _GeneratedQuestionSchema(BaseModel):
    question_type: Literal["likert", "multiple_choice", "free_text", "yes_no"]
    text: str
    rationale: str
    related_theme: str | None = None
    required: bool
    options: list[str] | None = None


class _QuestionnaireSchema(BaseModel):
    questions: list[_GeneratedQuestionSchema]


def _usage_to_dict(usage: Any) -> dict[str, Any] | None:
    """Maps a real SDK usage object to a plain dict, or None if the API
    didn't return one. Never invents a number for a missing field."""
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return None


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self) -> None:
        missing = [
            env_name
            for env_name, value in (
                ("OPENAI_API_KEY", settings.openai_api_key),
                ("OPENAI_TEXT_MODEL", settings.openai_text_model),
                ("OPENAI_TRANSCRIBE_MODEL", settings.openai_transcribe_model),
            )
            if not value
        ]
        if missing:
            raise OpenAIConfigurationError(
                "AI_PROVIDER=openai requires configuration that is missing: "
                f"{', '.join(missing)}. Set them in your .env (see .env.example) "
                "or switch AI_PROVIDER back to 'mock'."
            )

        from openai import OpenAI

        # Constructing the client makes no network call — safe to do here,
        # including from the /ready check via get_ai_provider().
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._text_model = settings.openai_text_model
        self._transcribe_model = settings.openai_transcribe_model

    def transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        with audio_path.open("rb") as audio_file:
            transcription = self._client.audio.transcriptions.create(
                model=self._transcribe_model,
                file=audio_file,
            )

        return {
            "transcript": transcription.text,
            "metadata": {
                "provider": self.name,
                "model": self._transcribe_model,
                "source_file": audio_path.name,
                "token_usage": _usage_to_dict(getattr(transcription, "usage", None)),
            },
        }

    def analyze_image(self, image_path: Path) -> ImageAnalysisResult:
        mime_type, _ = mimetypes.guess_type(image_path.name)
        mime_type = mime_type or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"

        response = self._client.responses.parse(
            model=self._text_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze this image. Extract any clearly visible text "
                                "verbatim (null if none is present), and give a concise, "
                                "factual visual description of what the image shows."
                            ),
                        },
                        {"type": "input_image", "image_url": data_url, "detail": "auto"},
                    ],
                }
            ],
            text_format=_ImageAnalysisSchema,
        )

        parsed = response.output_parsed
        if parsed is None:
            raise OpenAIProviderError(
                f"OpenAI image analysis returned no parsed structured output for "
                f"'{image_path.name}'."
            )

        return {
            "extracted_text": parsed.extracted_text,
            "visual_description": parsed.visual_description,
            "metadata": {
                "provider": self.name,
                "model": self._text_model,
                "source_file": image_path.name,
                "token_usage": _usage_to_dict(getattr(response, "usage", None)),
            },
        }

    def synthesize_project(self, assets: list[ProjectAssetContext]) -> ProjectSynthesisResult:
        context_by_asset_id = {asset["asset_id"]: asset for asset in assets}
        context_blob = "\n\n".join(
            f"--- asset_id={a['asset_id']} processing_result_id={a['processing_result_id']} "
            f"source_filename={a['source_filename']} modality={a['modality']} ---\n{a['text']}"
            for a in assets
        )

        instructions = (
            "You are synthesizing cross-asset project intelligence from already-"
            "processed feedback content. You are given asset excerpts, each labeled "
            "with its asset_id, processing_result_id, and source_filename. Produce a "
            "summary, top themes, sentiment summary, pain points, positive signals, "
            "questions/concerns, opportunities, and recommended actions, grounded only "
            "in the provided content. For each insight, add a matching evidence item. "
            "CRITICAL: an evidence item's asset_id, processing_result_id, and "
            "source_filename must be copied EXACTLY from one of the labeled assets "
            "above — never invent an id or filename. Its excerpt, if given, must be "
            "copied verbatim from that same asset's text — never paraphrased or invented."
        )

        response = self._client.responses.parse(
            model=self._text_model,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": context_blob},
            ],
            text_format=_ProjectSynthesisSchema,
        )

        parsed = response.output_parsed
        if parsed is None:
            raise OpenAIProviderError(
                "OpenAI project synthesis returned no parsed structured output."
            )

        evidence: list[dict[str, Any]] = []
        dropped = 0
        for item in parsed.evidence:
            source_asset = context_by_asset_id.get(item.asset_id)
            valid = (
                source_asset is not None
                and item.processing_result_id == source_asset["processing_result_id"]
                and item.source_filename == source_asset["source_filename"]
                and (not item.excerpt or item.excerpt in source_asset["text"])
            )
            if not valid:
                dropped += 1
                continue
            evidence.append(item.model_dump())

        return {
            "summary": parsed.summary,
            "top_themes": parsed.top_themes,
            "sentiment_summary": parsed.sentiment_summary,
            "pain_points": parsed.pain_points,
            "positive_signals": parsed.positive_signals,
            "questions_or_concerns": parsed.questions_or_concerns,
            "opportunities": parsed.opportunities,
            "recommended_actions": parsed.recommended_actions,
            "evidence": evidence,
            "metadata": {
                "provider": self.name,
                "model": self._text_model,
                "asset_count": len(assets),
                "evidence_returned_count": len(parsed.evidence),
                "evidence_dropped_invalid_reference_count": dropped,
                "token_usage": _usage_to_dict(getattr(response, "usage", None)),
            },
        }

    def generate_questionnaire(
        self, intelligence: IntelligenceContext
    ) -> QuestionnaireGenerationResult:
        # Literal strings a generated question's related_theme is allowed to
        # cite verbatim — mirrors the same rule MockAIProvider and CLAUDE.md
        # document: a theme, pain point, positive signal, concern,
        # opportunity, or the sentiment summary already in the input.
        allowed_related_themes = {
            value
            for value in (
                *intelligence["top_themes"],
                *intelligence["pain_points"],
                *intelligence["positive_signals"],
                *intelligence["questions_or_concerns"],
                *intelligence["opportunities"],
                intelligence["sentiment_summary"],
            )
            if value
        }

        instructions = (
            "You are generating a short follow-up questionnaire from already-"
            "generated project intelligence, provided below. Use only that material "
            "as your source — do not introduce new signals not present in it. "
            "CRITICAL: for each question, related_theme, if set, must be copied "
            "EXACTLY (verbatim) from the material below — never a paraphrase, a "
            "category label, or invented text."
        )
        context_blob = (
            f"summary: {intelligence['summary']}\n"
            f"top_themes: {intelligence['top_themes']}\n"
            f"sentiment_summary: {intelligence['sentiment_summary']}\n"
            f"pain_points: {intelligence['pain_points']}\n"
            f"positive_signals: {intelligence['positive_signals']}\n"
            f"questions_or_concerns: {intelligence['questions_or_concerns']}\n"
            f"opportunities: {intelligence['opportunities']}\n"
        )

        response = self._client.responses.parse(
            model=self._text_model,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": context_blob},
            ],
            text_format=_QuestionnaireSchema,
        )

        parsed = response.output_parsed
        if parsed is None:
            raise OpenAIProviderError(
                "OpenAI questionnaire generation returned no parsed structured output."
            )

        questions: list[GeneratedQuestion] = []
        dropped = 0
        for question in parsed.questions:
            if question.related_theme is not None and (
                question.related_theme not in allowed_related_themes
            ):
                dropped += 1
                continue
            questions.append(
                {
                    "question_type": question.question_type,
                    "text": question.text,
                    "rationale": question.rationale,
                    "related_theme": question.related_theme,
                    "required": question.required,
                    "options": question.options,
                }
            )

        return {
            "questions": questions,
            "metadata": {
                "provider": self.name,
                "model": self._text_model,
                "questions_returned_count": len(parsed.questions),
                "questions_dropped_invalid_related_theme_count": dropped,
                "token_usage": _usage_to_dict(getattr(response, "usage", None)),
            },
        }
