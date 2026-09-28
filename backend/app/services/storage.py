import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.models.asset import MODALITY_BY_EXTENSION, Asset
from app.models.intelligence import ProjectIntelligence
from app.models.processing import ProcessingResult
from app.models.project import Project
from app.models.questionnaire import Questionnaire
from app.models.report import ExecutiveReport

ALLOWED_EXTENSIONS = set(MODALITY_BY_EXTENSION)


class ProjectNotFoundError(Exception):
    pass


class AssetNotFoundError(Exception):
    pass


class ProcessingResultNotFoundError(Exception):
    pass


class ProjectIntelligenceNotFoundError(Exception):
    pass


class QuestionnaireNotFoundError(Exception):
    pass


class ReportNotFoundError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


class EmptyFileError(Exception):
    pass


# Every project/asset/processing-result/intelligence/questionnaire/report id
# in this codebase is either a uuid4 or a uuid5 hex string, so this pattern
# comfortably covers all legitimate ids while rejecting anything containing
# "/", "\", "..", or other characters that could influence path resolution.
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_id(value: str, not_found_exc: type[Exception]) -> str:
    """Guards every path built from a caller-supplied id against path
    traversal / arbitrary filesystem access. An invalid id is treated
    identically to a nonexistent one (same exception, same eventual 404) —
    a client can't distinguish "malformed id" from "id not found", which
    avoids leaking anything about *why* a request was rejected."""
    if not _SAFE_ID_PATTERN.match(value):
        raise not_found_exc(value)
    return value


def redact_absolute_paths(text: str) -> str:
    """Strips this machine's absolute repo path out of an error message
    before it is persisted or returned via the API. Some parsing libraries
    (Pillow, pypdf, mutagen, hachoir) embed the absolute file path in their
    exception text; without this, that path — including the local
    Windows username/directory layout — would leak into a persisted
    ProcessingResult/Questionnaire/ExecutiveReport `error` field and from
    there into an ordinary API response."""
    root = str(project_root())
    redacted = text.replace(root, "<project-root>")
    return redacted.replace(root.replace("\\", "/"), "<project-root>")


def project_root() -> Path:
    return Path(settings.data_dir).parent


def _data_root() -> Path:
    return Path(settings.data_dir) / "projects"


def _project_dir(project_id: str) -> Path:
    _validate_id(project_id, ProjectNotFoundError)
    return _data_root() / project_id


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def uploads_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "uploads"


def _assets_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "assets"


def _asset_file(project_id: str, asset_id: str) -> Path:
    _validate_id(asset_id, AssetNotFoundError)
    return _assets_dir(project_id) / f"{asset_id}.json"


def _processing_results_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "processing_results"


def _processing_result_file(project_id: str, result_id: str) -> Path:
    _validate_id(result_id, ProcessingResultNotFoundError)
    return _processing_results_dir(project_id) / f"{result_id}.json"


def _intelligence_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "intelligence"


def _intelligence_file(project_id: str, intelligence_id: str) -> Path:
    _validate_id(intelligence_id, ProjectIntelligenceNotFoundError)
    return _intelligence_dir(project_id) / f"{intelligence_id}.json"


def _questionnaires_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "questionnaires"


def _questionnaire_file(project_id: str, questionnaire_id: str) -> Path:
    _validate_id(questionnaire_id, QuestionnaireNotFoundError)
    return _questionnaires_dir(project_id) / f"{questionnaire_id}.json"


def _reports_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "reports"


def _report_file(project_id: str, report_id: str) -> Path:
    _validate_id(report_id, ReportNotFoundError)
    return _reports_dir(project_id) / f"{report_id}.json"


def report_pdf_path(project_id: str, report_id: str) -> Path:
    _validate_id(report_id, ReportNotFoundError)
    return _reports_dir(project_id) / f"{report_id}.pdf"


def runtime_tmp_dir() -> Path:
    """Scratch space for transient files (e.g. video keyframe/audio extraction).

    Lives under the gitignored data directory. Callers are responsible for
    cleaning up whatever subdirectory they create here.
    """
    tmp_dir = Path(settings.data_dir) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def create_project(name: str, description: str) -> Project:
    project = Project(id=str(uuid.uuid4()), name=name, description=description)

    project_dir = _project_dir(project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir(project.id).mkdir(parents=True, exist_ok=True)
    _assets_dir(project.id).mkdir(parents=True, exist_ok=True)
    _processing_results_dir(project.id).mkdir(parents=True, exist_ok=True)
    _intelligence_dir(project.id).mkdir(parents=True, exist_ok=True)
    _questionnaires_dir(project.id).mkdir(parents=True, exist_ok=True)
    _reports_dir(project.id).mkdir(parents=True, exist_ok=True)

    _project_file(project.id).write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return project


def get_project(project_id: str) -> Project:
    project_file = _project_file(project_id)
    if not project_file.exists():
        raise ProjectNotFoundError(project_id)

    return Project.model_validate_json(project_file.read_text(encoding="utf-8"))


def list_projects() -> list[Project]:
    data_root = _data_root()
    if not data_root.exists():
        return []

    projects = []
    for project_dir in sorted(data_root.iterdir()):
        project_file = project_dir / "project.json"
        if project_file.exists():
            projects.append(Project.model_validate_json(project_file.read_text(encoding="utf-8")))
    return sorted(projects, key=lambda project: project.created_at)


def safe_stored_filename(original_filename: str, extension: str) -> str:
    stem = Path(original_filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "file"
    return f"{uuid.uuid4().hex}_{safe_stem}{extension}"


def write_uploaded_file(project_id: str, original_filename: str, content: bytes) -> dict:
    """Validates project + extension, writes bytes to disk, returns write info."""
    # raises ProjectNotFoundError if missing
    get_project(project_id)

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(extension)

    target_dir = uploads_dir(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = safe_stored_filename(original_filename, extension)
    absolute_path = target_dir / stored_filename
    absolute_path.write_bytes(content)

    return {
        "extension": extension,
        "stored_filename": stored_filename,
        "absolute_path": absolute_path,
        "relative_path": str(absolute_path.relative_to(project_root())),
    }


def save_asset(asset: Asset) -> None:
    assets_dir = _assets_dir(asset.project_id)
    assets_dir.mkdir(parents=True, exist_ok=True)
    _asset_file(asset.project_id, asset.id).write_text(
        asset.model_dump_json(indent=2), encoding="utf-8"
    )


def get_asset(project_id: str, asset_id: str) -> Asset:
    get_project(project_id)

    asset_file = _asset_file(project_id, asset_id)
    if not asset_file.exists():
        raise AssetNotFoundError(asset_id)

    return Asset.model_validate_json(asset_file.read_text(encoding="utf-8"))


def list_assets(project_id: str) -> list[Asset]:
    get_project(project_id)

    assets_dir = _assets_dir(project_id)
    if not assets_dir.exists():
        return []

    assets = [
        Asset.model_validate_json(asset_file.read_text(encoding="utf-8"))
        for asset_file in sorted(assets_dir.glob("*.json"))
    ]
    return sorted(assets, key=lambda asset: asset.created_at)


def save_processing_result(result: ProcessingResult) -> None:
    results_dir = _processing_results_dir(result.project_id)
    results_dir.mkdir(parents=True, exist_ok=True)
    _processing_result_file(result.project_id, result.id).write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )


def get_processing_result(project_id: str, result_id: str) -> ProcessingResult:
    get_project(project_id)

    result_file = _processing_result_file(project_id, result_id)
    if not result_file.exists():
        raise ProcessingResultNotFoundError(result_id)

    return ProcessingResult.model_validate_json(result_file.read_text(encoding="utf-8"))


def list_processing_results(project_id: str) -> list[ProcessingResult]:
    get_project(project_id)

    results_dir = _processing_results_dir(project_id)
    if not results_dir.exists():
        return []

    results = [
        ProcessingResult.model_validate_json(result_file.read_text(encoding="utf-8"))
        for result_file in sorted(results_dir.glob("*.json"))
    ]
    return sorted(results, key=lambda result: result.created_at)


def save_project_intelligence(intelligence: ProjectIntelligence) -> None:
    intelligence_dir = _intelligence_dir(intelligence.project_id)
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    _intelligence_file(intelligence.project_id, intelligence.id).write_text(
        intelligence.model_dump_json(indent=2), encoding="utf-8"
    )


def get_project_intelligence(project_id: str, intelligence_id: str) -> ProjectIntelligence:
    get_project(project_id)

    intelligence_file = _intelligence_file(project_id, intelligence_id)
    if not intelligence_file.exists():
        raise ProjectIntelligenceNotFoundError(intelligence_id)

    return ProjectIntelligence.model_validate_json(intelligence_file.read_text(encoding="utf-8"))


def list_project_intelligence(project_id: str) -> list[ProjectIntelligence]:
    get_project(project_id)

    intelligence_dir = _intelligence_dir(project_id)
    if not intelligence_dir.exists():
        return []

    results = [
        ProjectIntelligence.model_validate_json(intelligence_file.read_text(encoding="utf-8"))
        for intelligence_file in sorted(intelligence_dir.glob("*.json"))
    ]
    return sorted(results, key=lambda result: result.created_at)


def save_questionnaire(questionnaire: Questionnaire) -> None:
    questionnaires_dir = _questionnaires_dir(questionnaire.project_id)
    questionnaires_dir.mkdir(parents=True, exist_ok=True)
    _questionnaire_file(questionnaire.project_id, questionnaire.id).write_text(
        questionnaire.model_dump_json(indent=2), encoding="utf-8"
    )


def get_questionnaire(project_id: str, questionnaire_id: str) -> Questionnaire:
    get_project(project_id)

    questionnaire_file = _questionnaire_file(project_id, questionnaire_id)
    if not questionnaire_file.exists():
        raise QuestionnaireNotFoundError(questionnaire_id)

    return Questionnaire.model_validate_json(questionnaire_file.read_text(encoding="utf-8"))


def list_questionnaires(project_id: str) -> list[Questionnaire]:
    get_project(project_id)

    questionnaires_dir = _questionnaires_dir(project_id)
    if not questionnaires_dir.exists():
        return []

    results = [
        Questionnaire.model_validate_json(questionnaire_file.read_text(encoding="utf-8"))
        for questionnaire_file in sorted(questionnaires_dir.glob("*.json"))
    ]
    return sorted(results, key=lambda result: result.created_at)


def save_report(report: ExecutiveReport) -> None:
    reports_dir = _reports_dir(report.project_id)
    reports_dir.mkdir(parents=True, exist_ok=True)
    _report_file(report.project_id, report.id).write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )


def get_report(project_id: str, report_id: str) -> ExecutiveReport:
    get_project(project_id)

    report_file = _report_file(project_id, report_id)
    if not report_file.exists():
        raise ReportNotFoundError(report_id)

    return ExecutiveReport.model_validate_json(report_file.read_text(encoding="utf-8"))


def list_reports(project_id: str) -> list[ExecutiveReport]:
    get_project(project_id)

    reports_dir = _reports_dir(project_id)
    if not reports_dir.exists():
        return []

    results = [
        ExecutiveReport.model_validate_json(report_file.read_text(encoding="utf-8"))
        for report_file in sorted(reports_dir.glob("*.json"))
    ]
    return sorted(results, key=lambda result: result.created_at)
