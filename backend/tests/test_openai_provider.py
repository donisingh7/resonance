"""Focused tests for the OpenAI provider adapter (P1.2).

No real network/API calls anywhere in this file. Where a test exercises
OpenAIProvider's request-mapping logic, `provider._client` is replaced with
a lightweight local stub before any method is called — the real
`openai.OpenAI()` client is only ever constructed (never invoked) to prove
that construction itself is network-free and config-validated correctly.
"""

from app.core.config import settings
from app.services.ai_providers import get_ai_provider
from app.services.ai_providers.mock_provider import MockAIProvider
from app.services.ai_providers.openai_provider import (
    OpenAIConfigurationError,
    OpenAIProvider,
    _EvidenceItemSchema,
    _GeneratedQuestionSchema,
    _ImageAnalysisSchema,
    _ProjectSynthesisSchema,
    _QuestionnaireSchema,
)


def _set_valid_openai_settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "fake-test-key-not-real")
    monkeypatch.setattr(settings, "openai_text_model", "fake-text-model")
    monkeypatch.setattr(settings, "openai_transcribe_model", "fake-transcribe-model")


# --- fakes for the OpenAI SDK client surface, no network involved --------


class _FakeUsage:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return self._data


class _FakeTranscription:
    def __init__(self, text, usage=None):
        self.text = text
        self.usage = usage


class _FakeResponse:
    def __init__(self, output_parsed, usage=None):
        self.output_parsed = output_parsed
        self.usage = usage


class _FakeTranscriptions:
    def __init__(self, result):
        self._result = result

    def create(self, **kwargs):
        return self._result


class _FakeAudio:
    def __init__(self, result):
        self.transcriptions = _FakeTranscriptions(result)


class _FakeResponses:
    def __init__(self, result):
        self._result = result

    def parse(self, **kwargs):
        return self._result


class _FakeOpenAIClient:
    def __init__(self, audio_result=None, responses_result=None):
        self.audio = _FakeAudio(audio_result)
        self.responses = _FakeResponses(responses_result)


def _provider_with_fake_client(monkeypatch, audio_result=None, responses_result=None):
    _set_valid_openai_settings(monkeypatch)
    provider = OpenAIProvider()
    provider._client = _FakeOpenAIClient(audio_result, responses_result)
    return provider


# --- provider selection / configuration -----------------------------------


def test_mock_provider_is_default_and_needs_no_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_text_model", None)
    monkeypatch.setattr(settings, "openai_transcribe_model", None)

    provider = get_ai_provider()

    assert isinstance(provider, MockAIProvider)
    assert provider.name == "mock"


def test_ai_provider_openai_resolves_openai_provider(monkeypatch):
    _set_valid_openai_settings(monkeypatch)

    provider = get_ai_provider()

    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"


def test_missing_openai_api_key_raises_clear_configuration_error(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_text_model", "fake-text-model")
    monkeypatch.setattr(settings, "openai_transcribe_model", "fake-transcribe-model")

    try:
        get_ai_provider()
        assert False, "expected OpenAIConfigurationError"
    except OpenAIConfigurationError as exc:
        assert "OPENAI_API_KEY" in str(exc)
        assert "fake-test-key-not-real" not in str(exc)


def test_unknown_provider_name_fails_clearly(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "not-a-real-provider")
    try:
        get_ai_provider()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not-a-real-provider" in str(exc)


# --- /ready behavior: mock vs openai ---------------------------------------


def test_ready_in_mock_mode_is_unaffected_by_missing_openai_config(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_text_model", None)
    monkeypatch.setattr(settings, "openai_transcribe_model", None)

    resp = client.get("/ready")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    provider_check = next(c for c in body["checks"] if c["name"] == "ai_provider_configured")
    assert provider_check["ok"] is True
    assert "mock" in provider_check["detail"]


def test_ready_in_openai_mode_missing_key_reports_not_ready(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_text_model", "fake-text-model")
    monkeypatch.setattr(settings, "openai_transcribe_model", "fake-transcribe-model")

    resp = client.get("/ready")

    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    provider_check = next(c for c in body["checks"] if c["name"] == "ai_provider_configured")
    assert provider_check["ok"] is False
    assert "OPENAI_API_KEY" in provider_check["detail"]


def test_ready_in_openai_mode_with_config_present_reports_ready(client, monkeypatch):
    _set_valid_openai_settings(monkeypatch)

    resp = client.get("/ready")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    provider_check = next(c for c in body["checks"] if c["name"] == "ai_provider_configured")
    assert provider_check["ok"] is True


# --- request/response mapping (stubbed client, no network) -----------------


def test_audio_transcription_maps_response_correctly(monkeypatch, tmp_path):
    fake_audio_file = tmp_path / "sample.mp3"
    fake_audio_file.write_bytes(b"not-real-audio-bytes")

    provider = _provider_with_fake_client(
        monkeypatch,
        audio_result=_FakeTranscription(
            text="hello from the fake transcription",
            usage=_FakeUsage({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}),
        ),
    )

    result = provider.transcribe_audio(fake_audio_file)

    assert result["transcript"] == "hello from the fake transcription"
    assert result["metadata"]["provider"] == "openai"
    assert result["metadata"]["model"] == "fake-transcribe-model"
    assert result["metadata"]["token_usage"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }


def test_image_analysis_maps_response_correctly(monkeypatch, tmp_path):
    fake_image_file = tmp_path / "sample.png"
    fake_image_file.write_bytes(b"not-real-png-bytes")

    parsed = _ImageAnalysisSchema(
        extracted_text="EXIT",
        visual_description="A photo of an exit sign.",
    )
    provider = _provider_with_fake_client(
        monkeypatch, responses_result=_FakeResponse(parsed, usage=None)
    )

    result = provider.analyze_image(fake_image_file)

    assert result["extracted_text"] == "EXIT"
    assert result["visual_description"] == "A photo of an exit sign."
    assert result["metadata"]["token_usage"] is None  # never fabricated


def test_project_synthesis_maps_output_and_drops_invalid_evidence(monkeypatch):
    contexts = [
        {
            "asset_id": "asset-1",
            "processing_result_id": "result-1",
            "source_filename": "feedback.txt",
            "modality": "document",
            "text": "The export feature is slow and frustrating.",
        }
    ]

    parsed = _ProjectSynthesisSchema(
        summary="Users report a slow export feature.",
        top_themes=["export speed"],
        sentiment_summary="leans negative",
        pain_points=["export is slow"],
        positive_signals=[],
        questions_or_concerns=[],
        opportunities=[],
        recommended_actions=["Investigate export performance."],
        evidence=[
            # valid: matches the supplied context exactly, excerpt is a
            # real substring of that asset's text
            _EvidenceItemSchema(
                category="pain_point",
                statement="export is slow",
                asset_id="asset-1",
                processing_result_id="result-1",
                source_filename="feedback.txt",
                excerpt="export feature is slow",
            ),
            # invalid: asset_id not present in the supplied context at all
            _EvidenceItemSchema(
                category="pain_point",
                statement="hallucinated",
                asset_id="asset-does-not-exist",
                processing_result_id="result-1",
                source_filename="feedback.txt",
                excerpt="anything",
            ),
            # invalid: excerpt is not a real substring of that asset's text
            _EvidenceItemSchema(
                category="pain_point",
                statement="invented excerpt",
                asset_id="asset-1",
                processing_result_id="result-1",
                source_filename="feedback.txt",
                excerpt="this text was never in the source content",
            ),
            # invalid: source_filename doesn't match the referenced asset
            _EvidenceItemSchema(
                category="pain_point",
                statement="wrong filename",
                asset_id="asset-1",
                processing_result_id="result-1",
                source_filename="someone-elses-file.txt",
                excerpt="export feature is slow",
            ),
        ],
    )
    provider = _provider_with_fake_client(
        monkeypatch, responses_result=_FakeResponse(parsed, usage=None)
    )

    result = provider.synthesize_project(contexts)

    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["asset_id"] == "asset-1"
    assert result["evidence"][0]["excerpt"] == "export feature is slow"
    assert result["metadata"]["evidence_dropped_invalid_reference_count"] == 3
    assert result["metadata"]["token_usage"] is None


def test_questionnaire_generation_maps_output_and_drops_invalid_related_theme(monkeypatch):
    intelligence_context = {
        "summary": "Summary text.",
        "top_themes": ["export speed"],
        "sentiment_summary": "leans negative",
        "pain_points": ["export is slow"],
        "positive_signals": [],
        "questions_or_concerns": [],
        "opportunities": [],
    }

    parsed = _QuestionnaireSchema(
        questions=[
            _GeneratedQuestionSchema(
                question_type="likert",
                text="How significant is the slow export issue?",
                rationale="Follows up on a reported pain point.",
                related_theme="export is slow",  # literal match, valid
                required=True,
                options=["1", "2", "3", "4", "5"],
            ),
            _GeneratedQuestionSchema(
                question_type="free_text",
                text="Tell us about something we never mentioned.",
                rationale="hallucinated",
                related_theme="a theme that was never in the intelligence context",
                required=False,
                options=None,
            ),
        ]
    )
    provider = _provider_with_fake_client(
        monkeypatch, responses_result=_FakeResponse(parsed, usage=None)
    )

    result = provider.generate_questionnaire(intelligence_context)

    assert len(result["questions"]) == 1
    assert result["questions"][0]["related_theme"] == "export is slow"
    assert result["metadata"]["questions_dropped_invalid_related_theme_count"] == 1
