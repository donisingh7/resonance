from app.models.evidence_integrity import EvidenceIntegrityIssue, EvidenceIntegrityReport
from app.services import intelligence as intelligence_service
from app.services import storage


def check_evidence_integrity(
    project_id: str, intelligence_id: str | None = None
) -> EvidenceIntegrityReport:
    """Verifies every evidence item on a project's intelligence result
    actually references a real asset, a real processing result that
    belongs to that asset, and that asset's own filename.

    This checks the existing S4 evidence architecture (EvidenceItem /
    ProjectIntelligence) as-is — it does not redesign it, repair a bad
    reference, or invent a replacement. Used by the evaluation harness and
    the regression test suite. Raises storage.ProjectIntelligenceNotFoundError
    / ValueError the same way intelligence.resolve_intelligence() does if
    no matching intelligence exists.
    """
    target = intelligence_service.resolve_intelligence(project_id, intelligence_id)

    assets_by_id = {asset.id: asset for asset in storage.list_assets(project_id)}
    results_by_id = {result.id: result for result in storage.list_processing_results(project_id)}

    issues: list[EvidenceIntegrityIssue] = []
    for index, item in enumerate(target.evidence):
        asset = assets_by_id.get(item.asset_id)
        result = results_by_id.get(item.processing_result_id)

        if asset is None:
            issues.append(
                EvidenceIntegrityIssue(
                    evidence_index=index,
                    category=item.category,
                    reason="asset_id does not reference a real asset in this project",
                    asset_id=item.asset_id,
                    processing_result_id=item.processing_result_id,
                )
            )
            continue
        if result is None:
            issues.append(
                EvidenceIntegrityIssue(
                    evidence_index=index,
                    category=item.category,
                    reason="processing_result_id does not reference a real processing result in this project",
                    asset_id=item.asset_id,
                    processing_result_id=item.processing_result_id,
                )
            )
            continue
        if result.asset_id != item.asset_id:
            issues.append(
                EvidenceIntegrityIssue(
                    evidence_index=index,
                    category=item.category,
                    reason="processing_result_id belongs to a different asset than asset_id",
                    asset_id=item.asset_id,
                    processing_result_id=item.processing_result_id,
                )
            )
            continue
        if item.source_filename != asset.original_filename:
            issues.append(
                EvidenceIntegrityIssue(
                    evidence_index=index,
                    category=item.category,
                    reason="source_filename does not match the referenced asset's original_filename",
                    asset_id=item.asset_id,
                    processing_result_id=item.processing_result_id,
                )
            )

    total = len(target.evidence)
    invalid = len(issues)
    return EvidenceIntegrityReport(
        intelligence_id=target.id,
        project_id=project_id,
        total_evidence_items=total,
        valid_evidence_items=total - invalid,
        invalid_evidence_items=invalid,
        all_valid=(invalid == 0),
        issues=issues,
    )
