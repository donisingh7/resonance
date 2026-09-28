from app.models.intelligence import IntelligenceStatus, ProjectIntelligence
from app.models.overview import ProjectOverview, StageStatus
from app.models.processing import ProcessingResult, ProcessingStatus
from app.models.questionnaire import Questionnaire, QuestionnaireStatus
from app.models.report import ExecutiveReport, ReportStatus
from app.services import storage


def _latest_result_by_asset(results: list[ProcessingResult]) -> dict[str, ProcessingResult]:
    """results is sorted ascending by created_at (storage convention), so a
    later entry for the same asset_id naturally overwrites an earlier one,
    leaving the most recent attempt per asset."""
    latest: dict[str, ProcessingResult] = {}
    for result in results:
        latest[result.asset_id] = result
    return latest


def intelligence_is_outdated(
    intelligence: ProjectIntelligence, completed_results: list[ProcessingResult]
) -> bool:
    """True if there are completed processing results that weren't part of
    the intelligence's own source set — i.e. assets were processed after
    intelligence was last generated."""
    completed_result_ids = {r.id for r in completed_results}
    return bool(completed_result_ids - set(intelligence.source_result_ids))


def build_project_overview(project_id: str) -> ProjectOverview:
    """Aggregates a project's real current state into a single snapshot.
    Every field is derived from persisted data; no progress percentage or
    fabricated metric is computed. Raises storage.ProjectNotFoundError if
    the project doesn't exist."""
    project = storage.get_project(project_id)
    assets = storage.list_assets(project_id)
    processing_results = storage.list_processing_results(project_id)
    intelligence_records = storage.list_project_intelligence(project_id)
    questionnaires = storage.list_questionnaires(project_id)
    reports = storage.list_reports(project_id)

    total_assets = len(assets)
    assets_by_modality: dict[str, int] = {}
    for asset in assets:
        assets_by_modality[asset.modality.value] = assets_by_modality.get(asset.modality.value, 0) + 1

    latest_by_asset = _latest_result_by_asset(processing_results)
    completed_results = [r for r in latest_by_asset.values() if r.status == ProcessingStatus.completed]
    failed_results = [r for r in latest_by_asset.values() if r.status == ProcessingStatus.failed]
    processed_assets = len(completed_results)
    failed_processing_assets = len(failed_results)
    pending_processing_assets = total_assets - len(latest_by_asset)

    latest_intelligence: ProjectIntelligence | None = (
        intelligence_records[-1] if intelligence_records else None
    )
    latest_questionnaire: Questionnaire | None = questionnaires[-1] if questionnaires else None
    latest_report: ExecutiveReport | None = reports[-1] if reports else None

    questionnaire_available = (
        latest_questionnaire is not None and latest_questionnaire.status == QuestionnaireStatus.completed
    )
    report_available = latest_report is not None and latest_report.status == ReportStatus.completed
    pdf_available = report_available and bool(latest_report.pdf_path) if latest_report else False

    blockers: list[str] = []
    warnings: list[str] = []

    if failed_processing_assets:
        warnings.append(
            f"{failed_processing_assets} asset(s) failed processing and were excluded from analysis."
        )

    if report_available and not pdf_available:
        warnings.append("PDF is not available for the latest executive report.")

    outdated = False
    if latest_intelligence is not None and latest_intelligence.status == IntelligenceStatus.completed:
        outdated = intelligence_is_outdated(latest_intelligence, completed_results)
        if outdated:
            warnings.append(
                "New processing results exist since project intelligence was last generated."
            )

    if total_assets == 0:
        overall_status = StageStatus.not_started
        current_stage = "upload_assets"
        next_action = "Upload at least one asset to begin."
        blockers.append("No assets uploaded yet.")
    elif pending_processing_assets > 0:
        overall_status = (
            StageStatus.ready
            if processed_assets == 0 and failed_processing_assets == 0
            else StageStatus.in_progress
        )
        current_stage = "process_assets"
        next_action = f"Process the {pending_processing_assets} pending asset(s)."
    elif processed_assets == 0:
        overall_status = StageStatus.blocked
        current_stage = "process_assets"
        next_action = "All asset processing attempts failed. Retry the failed asset(s)."
        blockers.append(f"All {failed_processing_assets} attempted asset(s) failed processing.")
    elif latest_intelligence is None:
        overall_status = StageStatus.ready
        current_stage = "generate_intelligence"
        next_action = "Generate project intelligence from the processed assets."
    elif latest_intelligence.status == IntelligenceStatus.failed:
        overall_status = StageStatus.failed
        current_stage = "generate_intelligence"
        next_action = "Project intelligence generation failed. Regenerate it."
        blockers.append(f"Intelligence generation failed: {latest_intelligence.error}")
    elif outdated:
        overall_status = StageStatus.partial
        current_stage = "generate_intelligence"
        next_action = "Regenerate project intelligence to include newly processed assets."
    elif latest_questionnaire is None:
        overall_status = StageStatus.ready
        current_stage = "generate_questionnaire"
        next_action = "Generate a follow-up questionnaire."
    elif latest_questionnaire.status == QuestionnaireStatus.failed:
        overall_status = StageStatus.partial
        current_stage = "generate_questionnaire"
        next_action = "Questionnaire generation failed. Regenerate it."
        warnings.append(f"Questionnaire generation failed: {latest_questionnaire.error}")
    elif latest_report is None:
        overall_status = StageStatus.ready
        current_stage = "generate_report"
        next_action = "Generate the executive report."
    elif latest_report.status == ReportStatus.failed:
        overall_status = StageStatus.failed
        current_stage = "generate_report"
        next_action = "Executive report generation failed. Regenerate it."
        blockers.append(f"Report generation failed: {latest_report.error}")
    else:
        overall_status = StageStatus.completed
        current_stage = "done"
        next_action = "Workflow complete. Explore intelligence, questionnaire, report, and evidence."

    return ProjectOverview(
        project_id=project_id,
        project_name=project.name,
        total_assets=total_assets,
        assets_by_modality=assets_by_modality,
        processed_assets=processed_assets,
        failed_processing_assets=failed_processing_assets,
        pending_processing_assets=pending_processing_assets,
        latest_intelligence_id=latest_intelligence.id if latest_intelligence else None,
        intelligence_status=latest_intelligence.status.value if latest_intelligence else None,
        active_provider=latest_intelligence.provider if latest_intelligence else None,
        questionnaire_available=questionnaire_available,
        latest_questionnaire_id=latest_questionnaire.id if latest_questionnaire else None,
        report_available=report_available,
        latest_report_id=latest_report.id if latest_report else None,
        pdf_available=pdf_available,
        overall_pipeline_status=overall_status,
        current_stage=current_stage,
        next_recommended_action=next_action,
        blockers=blockers,
        warnings=warnings,
    )
