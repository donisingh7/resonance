import uuid
from typing import Any

from app.models.intelligence import ProjectIntelligence
from app.models.project import Project
from app.models.questionnaire import Questionnaire
from app.models.report import ExecutiveReport, QuestionnaireSummary, ReportStatus, RiskFlag, RiskSeverity
from app.services import intelligence as intelligence_service
from app.services import storage
from app.services.report_pdf import render_report_pdf

# Below this fraction of a project's assets contributing to the analyzed
# context, the report is flagged as low-coverage.
LOW_COVERAGE_THRESHOLD = 0.5


def _deterministic_report_id(intelligence_id: str) -> str:
    """Stable id per intelligence_id, mirroring the idempotency strategy
    used elsewhere: regenerating a report for the same intelligence result
    overwrites the previous one instead of accumulating duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"resonance-report:{intelligence_id}"))


def _resolve_questionnaire(
    project_id: str, intelligence_id: str, questionnaire_id: str | None
) -> Questionnaire | None:
    if questionnaire_id:
        return storage.get_questionnaire(project_id, questionnaire_id)

    candidates = [
        q for q in storage.list_questionnaires(project_id) if q.intelligence_id == intelligence_id
    ]
    return candidates[-1] if candidates else None


def _build_source_coverage(project_id: str, intelligence: ProjectIntelligence) -> dict[str, Any]:
    total_assets = len(storage.list_assets(project_id))
    metadata = intelligence.processing_metadata
    return {
        "total_assets": total_assets,
        "total_processing_results": metadata.get("total_processing_results", 0),
        "completed_results": metadata.get("completed_results", 0),
        "assets_in_context": metadata.get("assets_in_context", 0),
        "failed_result_count": len(metadata.get("failed_result_ids", [])),
        "empty_content_result_count": len(metadata.get("empty_content_result_ids", [])),
        "asset_context_capped": metadata.get("asset_context_capped", False),
    }


def _build_executive_summary(
    project: Project, intelligence: ProjectIntelligence, coverage: dict[str, Any]
) -> str:
    if intelligence.status == "failed":
        return (
            f"[mock report] Project intelligence generation failed "
            f"({intelligence.error}); no executive summary could be produced."
        )
    if coverage["assets_in_context"] == 0:
        return (
            f"[mock report] No processed asset content was available for '{project.name}' "
            f"at the time this report was generated. Process and analyze assets, then "
            f"regenerate project intelligence before generating a meaningful report."
        )
    return (
        f"[mock report] Executive summary for '{project.name}': synthesized from "
        f"{coverage['assets_in_context']} of {coverage['total_assets']} project asset(s) "
        f"({coverage['completed_results']} completed processing result(s) considered). "
        f"{intelligence.summary}"
    )


def _build_risk_flags(
    intelligence: ProjectIntelligence,
    questionnaire: Questionnaire | None,
    coverage: dict[str, Any],
) -> list[RiskFlag]:
    """Deterministic, rule-based pipeline/data-quality flags only — this is
    NOT a content-moderation or safety classifier. Every flag is derived
    from real counts already recorded on the intelligence result / project
    state, never from inspecting or judging the content itself."""
    flags: list[RiskFlag] = []

    if intelligence.status == "failed":
        flags.append(
            RiskFlag(
                code="intelligence_generation_failed",
                severity=RiskSeverity.critical,
                message=f"The underlying project intelligence generation failed: {intelligence.error}",
            )
        )

    failed_ids = intelligence.processing_metadata.get("failed_result_ids", [])
    if failed_ids:
        flags.append(
            RiskFlag(
                code="processing_failures",
                severity=RiskSeverity.warning,
                message=(
                    f"{len(failed_ids)} asset(s) failed processing and were excluded from "
                    f"this analysis."
                ),
                details={"failed_result_ids": failed_ids},
            )
        )

    empty_ids = intelligence.processing_metadata.get("empty_content_result_ids", [])
    if empty_ids:
        flags.append(
            RiskFlag(
                code="empty_content_excluded",
                severity=RiskSeverity.info,
                message=(
                    f"{len(empty_ids)} processed asset(s) produced no usable text and were "
                    f"excluded from this analysis."
                ),
                details={"empty_content_result_ids": empty_ids},
            )
        )

    total_assets = coverage["total_assets"]
    assets_in_context = coverage["assets_in_context"]
    if total_assets == 0:
        flags.append(
            RiskFlag(
                code="no_assets",
                severity=RiskSeverity.critical,
                message="This project has no uploaded assets. The report has no source content.",
            )
        )
    elif assets_in_context == 0:
        flags.append(
            RiskFlag(
                code="no_source_coverage",
                severity=RiskSeverity.critical,
                message=(
                    "No processed asset content contributed to this analysis. Report "
                    "content is based on zero sources."
                ),
            )
        )
    elif assets_in_context / total_assets < LOW_COVERAGE_THRESHOLD:
        flags.append(
            RiskFlag(
                code="low_source_coverage",
                severity=RiskSeverity.warning,
                message=(
                    f"Only {assets_in_context} of {total_assets} project asset(s) contributed "
                    f"to this analysis; less than half of the project's assets are represented."
                ),
            )
        )

    if coverage.get("asset_context_capped"):
        flags.append(
            RiskFlag(
                code="asset_context_capped",
                severity=RiskSeverity.info,
                message=(
                    "This project exceeds the per-run analysis cap; only the earliest "
                    "completed results up to the cap were used."
                ),
            )
        )

    if assets_in_context > 0 and not intelligence.evidence:
        flags.append(
            RiskFlag(
                code="insufficient_supporting_evidence",
                severity=RiskSeverity.warning,
                message=(
                    "No evidence items were generated to support the synthesized insights "
                    "in this analysis."
                ),
            )
        )

    if intelligence.provider == "mock":
        flags.append(
            RiskFlag(
                code="mock_provider_output",
                severity=RiskSeverity.warning,
                message=(
                    "This report's insights are generated entirely by MockAIProvider, a "
                    "deterministic placeholder (word-frequency counting and fixed keyword "
                    "lists), not a real AI model. Do not treat sentiment/theme/pain-point "
                    "content as genuine analysis."
                ),
            )
        )

    if questionnaire is None:
        flags.append(
            RiskFlag(
                code="no_questionnaire_generated",
                severity=RiskSeverity.info,
                message="No follow-up questionnaire has been generated for this analysis yet.",
            )
        )
    elif questionnaire.status == "failed":
        flags.append(
            RiskFlag(
                code="questionnaire_generation_failed",
                severity=RiskSeverity.warning,
                message=f"Questionnaire generation failed: {questionnaire.error}",
            )
        )

    return flags


def generate_report(
    project_id: str, intelligence_id: str | None = None, questionnaire_id: str | None = None
) -> ExecutiveReport:
    """Builds and persists an ExecutiveReport from an existing
    ProjectIntelligence (and, if available, a Questionnaire derived from
    it). Raises storage.ProjectNotFoundError, storage.ProjectIntelligenceNotFoundError,
    or storage.QuestionnaireNotFoundError for unknown specific ids, or
    ValueError if no intelligence was specified and none exists yet.

    All factual sections (themes, pain points, evidence, etc.) are copied
    verbatim from the source ProjectIntelligence — nothing is regenerated
    or reinterpreted, so evidence traceability is preserved automatically.
    PDF rendering is attempted but isolated: a rendering failure is
    recorded as a risk flag rather than failing the whole report.
    """
    project = storage.get_project(project_id)
    target_intelligence = intelligence_service.resolve_intelligence(project_id, intelligence_id)
    target_questionnaire = _resolve_questionnaire(project_id, target_intelligence.id, questionnaire_id)

    coverage = _build_source_coverage(project_id, target_intelligence)

    questionnaire_summary = None
    if target_questionnaire:
        questionnaire_summary = QuestionnaireSummary(
            questionnaire_id=target_questionnaire.id,
            question_count=len(target_questionnaire.questions),
            status=target_questionnaire.status.value,
        )

    report = ExecutiveReport(
        id=_deterministic_report_id(target_intelligence.id),
        project_id=project_id,
        intelligence_id=target_intelligence.id,
        questionnaire_id=target_questionnaire.id if target_questionnaire else None,
        status=ReportStatus.completed,
        provider=target_intelligence.provider,
        executive_summary=_build_executive_summary(project, target_intelligence, coverage),
        source_coverage=coverage,
        overall_sentiment=target_intelligence.sentiment_summary,
        top_themes=target_intelligence.top_themes,
        pain_points=target_intelligence.pain_points,
        positive_signals=target_intelligence.positive_signals,
        questions_or_concerns=target_intelligence.questions_or_concerns,
        opportunities=target_intelligence.opportunities,
        recommended_actions=target_intelligence.recommended_actions,
        evidence=target_intelligence.evidence,
        questionnaire_summary=questionnaire_summary,
        risk_flags=_build_risk_flags(target_intelligence, target_questionnaire, coverage),
    )

    try:
        pdf_absolute_path = storage.report_pdf_path(project_id, report.id)
        render_report_pdf(report, project, pdf_absolute_path)
        report.pdf_path = str(pdf_absolute_path.relative_to(storage.project_root()))
    except Exception as exc:
        report.risk_flags.append(
            RiskFlag(
                code="pdf_generation_failed",
                severity=RiskSeverity.warning,
                message=f"PDF rendering failed for this report: {exc}",
            )
        )

    storage.save_report(report)
    return report
