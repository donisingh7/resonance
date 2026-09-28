import uuid
from typing import Any

from app.models.intelligence import EvidenceItem, IntelligenceStatus, ProjectIntelligence
from app.models.processing import ProcessingResult, ProcessingStatus
from app.services import storage
from app.services.ai_providers import get_ai_provider
from app.services.ai_providers.base import ProjectAssetContext

# Bounds so the synthesis input stays predictable in size regardless of
# how much text a project's assets have accumulated.
MAX_CHARS_PER_ASSET = 4000
MAX_ASSETS_IN_CONTEXT = 50


def _deterministic_intelligence_id(project_id: str, provider_name: str) -> str:
    """Stable id per (project, provider), mirroring processing.py's
    per-(asset, provider) idempotency strategy: regenerating overwrites the
    previous result instead of accumulating duplicates."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"resonance-intelligence:{project_id}:{provider_name}")
    )


def _extract_result_text(result: ProcessingResult) -> str:
    parts = [p for p in (result.transcript, result.extracted_text, result.visual_description) if p]
    return "\n\n".join(parts).strip()


def generate_project_intelligence(
    project_id: str, provider_name: str | None = None
) -> ProjectIntelligence:
    """Loads a project's successfully processed results, builds a bounded
    cross-asset context, and produces a persisted ProjectIntelligence.

    Raises storage.ProjectNotFoundError if the project doesn't exist. A
    provider failure during synthesis does not raise: it is captured as a
    failed ProjectIntelligence instead, mirroring processing.py's handling
    of per-asset provider failures. A project with no usable processed
    content yields a completed-but-empty result rather than an error.
    """
    storage.get_project(project_id)

    provider = get_ai_provider(provider_name)
    intelligence_id = _deterministic_intelligence_id(project_id, provider.name)

    all_results = storage.list_processing_results(project_id)
    assets_by_id = {asset.id: asset for asset in storage.list_assets(project_id)}

    completed_results = [r for r in all_results if r.status == ProcessingStatus.completed]
    failed_results = [r for r in all_results if r.status == ProcessingStatus.failed]
    considered_results = completed_results[:MAX_ASSETS_IN_CONTEXT]

    contexts: list[ProjectAssetContext] = []
    empty_content_result_ids: list[str] = []
    for result in considered_results:
        text = _extract_result_text(result)
        if not text:
            empty_content_result_ids.append(result.id)
            continue
        asset = assets_by_id.get(result.asset_id)
        contexts.append(
            {
                "asset_id": result.asset_id,
                "processing_result_id": result.id,
                "source_filename": asset.original_filename if asset else result.asset_id,
                "modality": result.modality.value,
                "text": text[:MAX_CHARS_PER_ASSET],
            }
        )

    base_metadata: dict[str, Any] = {
        "total_processing_results": len(all_results),
        "completed_results": len(completed_results),
        "failed_result_ids": [r.id for r in failed_results],
        "empty_content_result_ids": empty_content_result_ids,
        "assets_in_context": len(contexts),
        "asset_context_capped": len(completed_results) > MAX_ASSETS_IN_CONTEXT,
    }

    if not contexts:
        result = ProjectIntelligence(
            id=intelligence_id,
            project_id=project_id,
            status=IntelligenceStatus.completed,
            provider=provider.name,
            source_result_ids=[],
            summary=(
                "No processed asset content is available for this project yet. "
                "Process at least one asset (with extracted text, transcript, or "
                "visual description) before generating project intelligence."
            ),
            processing_metadata=base_metadata,
        )
        storage.save_project_intelligence(result)
        return result

    try:
        synthesis = provider.synthesize_project(contexts)
        valid_result_ids = {c["processing_result_id"] for c in contexts}
        evidence_items = [
            EvidenceItem(**item)
            for item in synthesis["evidence"]
            if item["processing_result_id"] in valid_result_ids
        ]

        result = ProjectIntelligence(
            id=intelligence_id,
            project_id=project_id,
            status=IntelligenceStatus.completed,
            provider=provider.name,
            source_result_ids=[c["processing_result_id"] for c in contexts],
            summary=synthesis["summary"],
            top_themes=synthesis["top_themes"],
            sentiment_summary=synthesis["sentiment_summary"],
            pain_points=synthesis["pain_points"],
            positive_signals=synthesis["positive_signals"],
            questions_or_concerns=synthesis["questions_or_concerns"],
            opportunities=synthesis["opportunities"],
            recommended_actions=synthesis["recommended_actions"],
            evidence=evidence_items,
            processing_metadata={**base_metadata, **synthesis["metadata"]},
        )
    except Exception as exc:
        result = ProjectIntelligence(
            id=intelligence_id,
            project_id=project_id,
            status=IntelligenceStatus.failed,
            provider=provider.name,
            source_result_ids=[c["processing_result_id"] for c in contexts],
            processing_metadata=base_metadata,
            error=str(exc),
        )

    storage.save_project_intelligence(result)
    return result
