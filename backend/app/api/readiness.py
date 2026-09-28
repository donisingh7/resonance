from fastapi import APIRouter, Response

from app.models.readiness import ReadinessReport
from app.services import readiness

router = APIRouter()


@router.get("/ready", response_model=ReadinessReport)
def readiness_check(response: Response):
    report = readiness.build_readiness_report()
    if not report.ready:
        response.status_code = 503
    return report
