from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai import router as ai_router
from app.api.branch_activity import router as branch_activity_router
from app.api.career_assets import router as career_assets_router
from app.api.health import router as health_router
from app.api.github_webhooks import router as github_webhooks_router
from app.api.github_items import router as github_items_router
from app.api.milestone_evidence import router as milestone_evidence_router
from app.api.outcomes import router as outcomes_router
from app.api.projects import router as projects_router
from app.api.reports import router as reports_router
from app.api.work_logs import router as work_logs_router
from app.core.config import get_settings, validate_runtime_settings

settings = get_settings()
validate_runtime_settings(settings)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "API for the worktrace MVP. "
        "Projects, work logs, outcomes, career assets, and reports are available; "
        "file ingestion, document analysis, and RAG are not implemented in this slice."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(github_webhooks_router)
app.include_router(github_items_router)
app.include_router(ai_router)
app.include_router(projects_router)
app.include_router(branch_activity_router)
app.include_router(milestone_evidence_router)
app.include_router(career_assets_router)
app.include_router(outcomes_router)
app.include_router(reports_router)
app.include_router(work_logs_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "message": "worktrace backend is running",
        "scope": "personal work evidence and career asset MVP; file ingestion, document analysis, and RAG are not implemented",
    }
