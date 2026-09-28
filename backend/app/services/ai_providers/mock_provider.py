import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.services.ai_providers.base import (
    AIProvider,
    GeneratedQuestion,
    ImageAnalysisResult,
    IntelligenceContext,
    ProjectAssetContext,
    ProjectEvidenceItem,
    ProjectSynthesisResult,
    QuestionnaireGenerationResult,
    TranscriptionResult,
)

# Generic stopwords plus MockAIProvider's own boilerplate phrasing (so its
# placeholder transcript/description text doesn't drown out real PDF/TXT
# content when picking "top themes").
_STOPWORDS = {
    "this", "that", "these", "those", "with", "from", "have", "has", "had",
    "were", "was", "are", "is", "be", "been", "being", "will", "would",
    "could", "should", "which", "what", "when", "where", "while", "about",
    "into", "onto", "your", "their", "there", "here", "also", "than", "then",
    "them", "they", "each", "some", "such", "only", "just", "more", "most",
    "over", "under", "does", "not", "for", "and", "the", "you", "our",
    "mock", "mockaiprovider", "perform", "real", "speech", "text", "speech-to-text",
    "placeholder", "transcription", "vision", "analysis", "bytes", "provider",
    "description", "transcript", "format", "image",
}

_PAIN_KEYWORDS = [
    "problem", "issue", "bug", "fail", "failure", "slow", "confus",
    "difficult", "frustrat", "broken", "complain", "crash", "error", "annoy",
]
_POSITIVE_KEYWORDS = [
    "great", "love", "excellent", "good", "easy", "helpful", "amazing",
    "smooth", "impress", "fantastic", "wonderful", "enjoy", "useful", "intuitive",
]


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z']{4,}", text.lower()) if w not in _STOPWORDS}


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _is_placeholder(text: str) -> bool:
    """True for MockAIProvider's own 'nothing detected' filler strings
    (e.g. "[mock] No pain-point keywords detected..."), so questionnaire
    generation doesn't ask a follow-up question about a non-finding."""
    return text.startswith("[mock] No ")


def _find_excerpt(text: str, keyword: str, radius: int = 80) -> str:
    lowered = text.lower()
    idx = lowered.find(keyword.lower())
    if idx == -1:
        return text[:160].strip()
    start = max(0, idx - radius)
    end = min(len(text), idx + len(keyword) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


class MockAIProvider(AIProvider):
    """Deterministic stand-in for a real transcription/vision provider.

    Produces clearly-labeled placeholder output derived from the file
    itself (name, size, dimensions) so behavior is stable and repeatable
    without any external API or credentials. Used as the default provider
    so the app is fully runnable offline.
    """

    name = "mock"

    def transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        size_bytes = audio_path.stat().st_size
        transcript = (
            f"[mock transcript] MockAIProvider does not perform real speech-to-text. "
            f"Placeholder transcription for '{audio_path.name}' ({size_bytes} bytes)."
        )
        return {
            "transcript": transcript,
            "metadata": {
                "mock": True,
                "source_file": audio_path.name,
                "size_bytes": size_bytes,
                # No real model call was made, so there is no token usage to
                # report. Explicitly null rather than omitted, so a future
                # real provider has an established field to populate instead
                # of this looking like an oversight.
                "token_usage": None,
            },
        }

    def analyze_image(self, image_path: Path) -> ImageAnalysisResult:
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
            image_format = img.format

        visual_description = (
            f"[mock description] MockAIProvider does not perform real vision analysis. "
            f"Placeholder description for a {width}x{height} {image_format} image "
            f"'{image_path.name}'."
        )
        return {
            "extracted_text": None,
            "visual_description": visual_description,
            "metadata": {
                "mock": True,
                "source_file": image_path.name,
                "width": width,
                "height": height,
                "format": image_format,
                "token_usage": None,
            },
        }

    def synthesize_project(
        self, assets: list[ProjectAssetContext]
    ) -> ProjectSynthesisResult:
        """Deterministic, keyword-heuristic cross-asset synthesis.

        Not real AI analysis: themes come from word-frequency counting,
        sentiment/pain/positive signals come from fixed keyword lists, and
        every evidence excerpt is a verbatim substring of the asset text it
        cites. No content is invented.
        """
        evidence: list[ProjectEvidenceItem] = []

        word_counts: Counter[str] = Counter()
        for asset in assets:
            word_counts.update(_tokenize(asset["text"]))

        top_theme_words = [word for word, _ in word_counts.most_common(5)]
        top_themes: list[str] = []
        for word in top_theme_words:
            contributing = [a for a in assets if word in a["text"].lower()]
            if not contributing:
                continue
            statement = f"[mock] '{word}' mentioned in {len(contributing)} asset(s)"
            top_themes.append(statement)
            first = contributing[0]
            evidence.append(
                {
                    "category": "theme",
                    "statement": statement,
                    "asset_id": first["asset_id"],
                    "processing_result_id": first["processing_result_id"],
                    "source_filename": first["source_filename"],
                    "excerpt": _find_excerpt(first["text"], word),
                }
            )

        def _keyword_bucket(keywords: list[str], category: str, label: str) -> list[str]:
            statements: list[str] = []
            for keyword in keywords:
                contributing = [a for a in assets if keyword in a["text"].lower()]
                if not contributing:
                    continue
                statement = (
                    f"[mock] {label} signal: '{keyword}' found in "
                    f"{len(contributing)} asset(s)."
                )
                statements.append(statement)
                first = contributing[0]
                evidence.append(
                    {
                        "category": category,
                        "statement": statement,
                        "asset_id": first["asset_id"],
                        "processing_result_id": first["processing_result_id"],
                        "source_filename": first["source_filename"],
                        "excerpt": _find_excerpt(first["text"], keyword),
                    }
                )
                if len(statements) >= 5:
                    break
            return statements

        pain_points = _keyword_bucket(_PAIN_KEYWORDS, "pain_point", "Possible pain-point")
        positive_signals = _keyword_bucket(_POSITIVE_KEYWORDS, "positive_signal", "Possible positive")

        questions_or_concerns: list[str] = []
        for asset in assets:
            for sentence in _split_sentences(asset["text"]):
                if "?" not in sentence:
                    continue
                statement = f"[mock] Question/concern noted: \"{sentence.strip()[:200]}\""
                if statement in questions_or_concerns:
                    continue
                questions_or_concerns.append(statement)
                evidence.append(
                    {
                        "category": "question_or_concern",
                        "statement": statement,
                        "asset_id": asset["asset_id"],
                        "processing_result_id": asset["processing_result_id"],
                        "source_filename": asset["source_filename"],
                        "excerpt": sentence.strip()[:200],
                    }
                )
                if len(questions_or_concerns) >= 5:
                    break
            if len(questions_or_concerns) >= 5:
                break

        opportunities: list[str] = []
        for word in top_theme_words[:2]:
            contributing = [a for a in assets if word in a["text"].lower()]
            if not contributing:
                continue
            statement = f"[mock] Consider exploring opportunities related to '{word}' further."
            opportunities.append(statement)
            first = contributing[0]
            evidence.append(
                {
                    "category": "opportunity",
                    "statement": statement,
                    "asset_id": first["asset_id"],
                    "processing_result_id": first["processing_result_id"],
                    "source_filename": first["source_filename"],
                    "excerpt": _find_excerpt(first["text"], word),
                }
            )

        recommended_actions: list[str] = []
        if pain_points:
            recommended_actions.append(
                f"[mock] Prioritize investigating the {len(pain_points)} "
                f"potential pain-point signal(s) identified above."
            )
        if positive_signals:
            recommended_actions.append(
                f"[mock] Reinforce the {len(positive_signals)} positive signal(s) identified above."
            )
        if questions_or_concerns:
            recommended_actions.append(
                f"[mock] Follow up on the {len(questions_or_concerns)} "
                f"outstanding question(s)/concern(s) raised above."
            )
        recommended_actions.append(
            "[mock] Review full per-asset processing results for complete context — "
            "this synthesis is deterministic placeholder output, not real AI analysis."
        )

        if len(positive_signals) > len(pain_points):
            sentiment_label = "leans positive"
        elif len(pain_points) > len(positive_signals):
            sentiment_label = "leans negative"
        else:
            sentiment_label = "mixed/neutral"
        sentiment_summary = (
            f"[mock sentiment] heuristic keyword counts — "
            f"positive_signal_matches={len(positive_signals)}, "
            f"pain_point_matches={len(pain_points)} → {sentiment_label}. "
            f"Based on fixed keyword matching only, not real sentiment analysis."
        )

        modalities = sorted({a["modality"] for a in assets})
        total_chars = sum(len(a["text"]) for a in assets)
        summary = (
            f"[mock project synthesis] Deterministic placeholder synthesis (not real AI "
            f"analysis) across {len(assets)} processed asset(s) with usable content "
            f"({', '.join(modalities)}). Total input characters considered: {total_chars}."
        )

        metadata: dict[str, Any] = {
            "mock": True,
            "asset_count": len(assets),
            "keyword_heuristic": True,
            "total_input_characters": total_chars,
            "token_usage": None,
        }

        return {
            "summary": summary,
            "top_themes": top_themes or ["[mock] No recurring theme words detected in available content."],
            "sentiment_summary": sentiment_summary,
            "pain_points": pain_points or ["[mock] No pain-point keywords detected in available content."],
            "positive_signals": positive_signals
            or ["[mock] No positive-signal keywords detected in available content."],
            "questions_or_concerns": questions_or_concerns
            or ["[mock] No explicit questions detected in available content."],
            "opportunities": opportunities
            or ["[mock] No specific opportunity signals detected; process more assets for richer input."],
            "recommended_actions": recommended_actions,
            "evidence": evidence,
            "metadata": metadata,
        }

    def generate_questionnaire(
        self, intelligence: IntelligenceContext
    ) -> QuestionnaireGenerationResult:
        """Deterministic follow-up questionnaire derived from already-generated
        ProjectIntelligence fields. Every question's `related_theme` is a
        literal string taken from `intelligence` — no new signal is invented,
        this only reformulates existing mock output into follow-up prompts.
        """
        questions: list[GeneratedQuestion] = []

        likert_options = ["1 - Not significant", "2", "3", "4", "5 - Extremely significant"]
        relevance_options = ["Highly relevant", "Somewhat relevant", "Not relevant", "Unsure"]
        yes_no_options = ["Yes", "No"]

        for theme in [t for t in intelligence["top_themes"] if not _is_placeholder(t)][:3]:
            questions.append(
                {
                    "question_type": "multiple_choice",
                    "text": f"[mock] How relevant is the following theme to your current priorities: \"{theme}\"?",
                    "rationale": (
                        f"[mock] Generated because the project intelligence flagged this as a "
                        f"top theme: \"{theme}\"."
                    ),
                    "related_theme": theme,
                    "required": True,
                    "options": relevance_options,
                }
            )

        for pain_point in [p for p in intelligence["pain_points"] if not _is_placeholder(p)][:5]:
            questions.append(
                {
                    "question_type": "likert",
                    "text": (
                        f"[mock] On a scale of 1-5, how significant is this reported pain point "
                        f"for you: \"{pain_point}\"?"
                    ),
                    "rationale": (
                        f"[mock] Generated to validate a possible pain-point signal identified "
                        f"in the project intelligence: \"{pain_point}\"."
                    ),
                    "related_theme": pain_point,
                    "required": True,
                    "options": likert_options,
                }
            )

        for concern in [c for c in intelligence["questions_or_concerns"] if not _is_placeholder(c)][:3]:
            questions.append(
                {
                    "question_type": "free_text",
                    "text": f"[mock] Can you elaborate on this open question or concern: \"{concern}\"?",
                    "rationale": (
                        f"[mock] Generated to follow up on an unresolved question/concern noted "
                        f"in the project intelligence: \"{concern}\"."
                    ),
                    "related_theme": concern,
                    "required": False,
                    "options": None,
                }
            )

        for opportunity in [o for o in intelligence["opportunities"] if not _is_placeholder(o)][:2]:
            questions.append(
                {
                    "question_type": "yes_no",
                    "text": f"[mock] Should this opportunity be pursued further: \"{opportunity}\"?",
                    "rationale": (
                        f"[mock] Generated from an opportunity signal identified in the project "
                        f"intelligence: \"{opportunity}\"."
                    ),
                    "related_theme": opportunity,
                    "required": True,
                    "options": yes_no_options,
                }
            )

        if intelligence["sentiment_summary"]:
            questions.append(
                {
                    "question_type": "yes_no",
                    "text": (
                        f"[mock] Does this sentiment assessment match your experience: "
                        f"\"{intelligence['sentiment_summary']}\"?"
                    ),
                    "rationale": "[mock] Generated to validate the heuristic sentiment assessment.",
                    "related_theme": intelligence["sentiment_summary"],
                    "required": False,
                    "options": yes_no_options,
                }
            )

        questions.append(
            {
                "question_type": "free_text",
                "text": "[mock] Is there any other context we should be aware of that wasn't captured above?",
                "rationale": (
                    "[mock] Always included to surface missing context not captured by the "
                    "deterministic mock synthesis."
                ),
                "related_theme": None,
                "required": False,
                "options": None,
            }
        )

        return {
            "questions": questions,
            "metadata": {"mock": True, "question_count": len(questions), "token_usage": None},
        }
