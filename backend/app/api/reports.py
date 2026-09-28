from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.report import ExecutiveReport, ReportGenerateRequest
from app.services import report, storage

router = APIRouter(prefix="/projects/{project_id}/reports", tags=["reports"])


@router.post("", response_model=ExecutiveReport)
def generate_report(project_id: str, payload: ReportGenerateRequest = ReportGenerateRequest()):
    try:
        return report.generate_report(project_id, payload.intelligence_id, payload.questionnaire_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.ProjectIntelligenceNotFoundError:
        raise HTTPException(status_code=404, detail="Project intelligence not found")
    except storage.QuestionnaireNotFoundError:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[ExecutiveReport])
def list_reports(project_id: str):
    try:
        return storage.list_reports(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{report_id}", response_model=ExecutiveReport)
def get_report(project_id: str, report_id: str):
    try:
        return storage.get_report(project_id, report_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found")


@router.get("/{report_id}/pdf")
def get_report_pdf(project_id: str, report_id: str):
    try:
        target_report = storage.get_report(project_id, report_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found")

    if not target_report.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not available for this report")

    pdf_path = storage.project_root() / target_report.pdf_path
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")

    return FileResponse(
        pdf_path, media_type="application/pdf", filename=f"resonance_report_{report_id}.pdf"
    )
