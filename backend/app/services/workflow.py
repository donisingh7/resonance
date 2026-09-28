from datetime import datetime, timezone

from app.core.observability import track_operation
from app.models.intelligence import IntelligenceStatus
from app.models.processing import ProcessingStatus
from app.models.workflow import WorkflowRunResult
from app.services import intelligence as intelligence_service
from app.services import overview as overview_service
from app.services import processing, questionnaire as questionnaire_service
from app.services import report as report_service
from app.services import storage


def run_workflow(project_id: str) -> WorkflowRunResult:
    """Synchronously executes whichever pipeline steps are missing, in
    order: process pending assets -> (re)generate intelligence if missing/
    failed/outdated -> generate a questionnaire if none exists yet for the
    current intelligence -> generate a report if none exists yet for the
    current (intelligence, questionnaire) pair.

    Idempotent by construction: each step only acts when there is
    something new to do, and questionnaire generation in particular is
    skipped entirely once one exists for the current intelligence, so
    manual edits are never silently overwritten by re-running this. Raises
    storage.ProjectNotFoundError if the project doesn't exist.
    """
    started_at = datetime.now(timezone.utc)
    storage.get_project(project_id)

    stages_attempted: list[str] = []
    stages_completed: list[str] = []
    stages_skipped: list[str] = []
    warnings: list[str] = []
    successes: list[str] = []
    failures: list[str] = []

    with track_operation("run_workflow", project_id=project_id) as op:
        # 1. Process any asset with no processing attempt yet. Already-completed
        # (or already-failed) results are left alone — retrying a failure is a
        # deliberate, separate action (POST .../assets/{id}/retry), not implied
        # by re-running the whole workflow.
        stages_attempted.append("process_assets")
        assets = storage.list_assets(project_id)
        attempted_asset_ids = {r.asset_id for r in storage.list_processing_results(project_id)}
        pending_assets = [a for a in assets if a.id not in attempted_asset_ids]
        op["total_assets"] = len(assets)

        if not pending_assets:
            stages_skipped.append("process_assets")
        else:
            for asset in pending_assets:
                try:
                    result = processing.process_asset(project_id, asset.id)
                    if result.status == ProcessingStatus.completed:
                        successes.append(asset.id)
                    else:
                        failures.append(asset.id)
                        warnings.append(
                            f"Asset '{asset.original_filename}' ({asset.id}) failed processing: {result.error}"
                        )
                except Exception as exc:
                    failures.append(asset.id)
                    warnings.append(
                        f"Asset '{asset.original_filename}' ({asset.id}) raised an unexpected "
                        f"error during processing: {storage.redact_absolute_paths(str(exc))}"
                    )
            stages_completed.append("process_assets")

        op["assets_processed"] = len(successes)
        op["assets_failed"] = len(failures)
        op["assets_skipped"] = len(assets) - len(pending_assets)

        # 2. Intelligence: (re)generate if missing, failed, or stale relative to
        # the processing results that now exist.
        stages_attempted.append("generate_intelligence")
        intelligence_records = storage.list_project_intelligence(project_id)
        latest_intelligence = intelligence_records[-1] if intelligence_records else None
        completed_results = [
            r
            for r in storage.list_processing_results(project_id)
            if r.status == ProcessingStatus.completed
        ]

        needs_intelligence = (
            latest_intelligence is None
            or latest_intelligence.status == IntelligenceStatus.failed
            or (
                latest_intelligence.status == IntelligenceStatus.completed
                and overview_service.intelligence_is_outdated(latest_intelligence, completed_results)
            )
        )

        if needs_intelligence:
            latest_intelligence = intelligence_service.generate_project_intelligence(project_id)
            intelligence_action = "generated"
            stages_completed.append("generate_intelligence")
        else:
            intelligence_action = "reused"
            stages_skipped.append("generate_intelligence")

        intelligence_id = latest_intelligence.id if latest_intelligence else None
        intelligence_ready = (
            latest_intelligence is not None
            and latest_intelligence.status == IntelligenceStatus.completed
        )
        if latest_intelligence is not None and not intelligence_ready:
            warnings.append(f"Project intelligence generation failed: {latest_intelligence.error}")

        # 3. Questionnaire: generate only if none exists yet for this
        # intelligence. Never regenerate an existing one here — that would
        # silently discard manual edits. Regenerating is a separate, explicit
        # user action via the questionnaire UI/endpoint.
        stages_attempted.append("generate_questionnaire")
        questionnaire_id: str | None = None
        questionnaire_action = "skipped"
        if intelligence_ready:
            existing_questionnaires = [
                q
                for q in storage.list_questionnaires(project_id)
                if q.intelligence_id == latest_intelligence.id
            ]
            if existing_questionnaires:
                questionnaire_id = existing_questionnaires[-1].id
                questionnaire_action = "reused"
                stages_skipped.append("generate_questionnaire")
            else:
                generated_questionnaire = questionnaire_service.generate_questionnaire(
                    project_id, latest_intelligence.id
                )
                questionnaire_id = generated_questionnaire.id
                questionnaire_action = "generated"
                stages_completed.append("generate_questionnaire")
        else:
            stages_skipped.append("generate_questionnaire")

        # 4. Report: generate if none exists yet for this (intelligence,
        # questionnaire) pairing; regenerate only if the linked questionnaire
        # changed since the last report (e.g. a questionnaire was generated
        # after an earlier report ran with none).
        stages_attempted.append("generate_report")
        report_id: str | None = None
        report_action = "skipped"
        if intelligence_ready:
            existing_reports = [
                r for r in storage.list_reports(project_id) if r.intelligence_id == latest_intelligence.id
            ]
            current_report = existing_reports[-1] if existing_reports else None
            report_is_current = (
                current_report is not None and current_report.questionnaire_id == questionnaire_id
            )

            if report_is_current:
                report_id = current_report.id
                report_action = "reused"
                stages_skipped.append("generate_report")
            else:
                generated_report = report_service.generate_report(project_id, latest_intelligence.id)
                report_id = generated_report.id
                report_action = "generated" if current_report is None else "updated"
                stages_completed.append("generate_report")
        else:
            stages_skipped.append("generate_report")

        finished_at = datetime.now(timezone.utc)
        final_overview = overview_service.build_project_overview(project_id)

        op["stages_completed"] = len(stages_completed)
        op["stages_skipped"] = len(stages_skipped)
        op["status"] = "completed" if not failures else "partial"

    return WorkflowRunResult(
        project_id=project_id,
        started_at=started_at,
        finished_at=finished_at,
        stages_attempted=stages_attempted,
        stages_completed=stages_completed,
        stages_skipped=stages_skipped,
        asset_processing_successes=successes,
        asset_processing_failures=failures,
        intelligence_id=intelligence_id,
        intelligence_action=intelligence_action,
        questionnaire_id=questionnaire_id,
        questionnaire_action=questionnaire_action,
        report_id=report_id,
        report_action=report_action,
        warnings=warnings,
        overview=final_overview,
    )
