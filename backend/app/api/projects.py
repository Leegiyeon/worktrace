import psycopg
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.errors import http_error
from app.api.security import require_report_access
from app.core.config import Settings, get_settings
from app.schemas.projects import (
    GitHubCommit,
    ProjectCreate,
    ProjectGitHubStatus,
    ProjectLifecycle,
    ProjectLifecycleConfirm,
    ProjectMilestone,
    ProjectMilestoneCreate,
    ProjectMilestoneUpdate,
    ProjectSummary,
    ProjectTask,
    ProjectTaskCreate,
    ProjectTaskUpdate,
    ProjectUpdate,
    RepositorySource,
    RepositorySourceCreate,
)
from app.services.github_webhooks import GitHubDeliveryNotFoundError, get_project_github_status, reprocess_github_delivery
from app.services.projects import (
    ProjectLifecycleConflictError,
    ProjectLifecycleRequestConflictError,
    ProjectLifecycleValidationError,
    ProjectMilestoneNotFoundError,
    ProjectMilestoneWeightError,
    ProjectNotFoundError,
    ProjectStatusUpdateForbiddenError,
    ProjectTaskNotFoundError,
    RepositorySourceConflictError,
    create_project,
    create_project_milestone,
    create_project_task,
    delete_project,
    delete_project_milestone,
    delete_project_task,
    confirm_project_lifecycle,
    get_project,
    get_project_lifecycle,
    get_repository_source,
    list_project_commits,
    list_project_milestones,
    list_project_tasks,
    list_projects,
    update_project,
    update_project_milestone,
    update_project_task,
    upsert_repository_source,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_not_found() -> Exception:
    return http_error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND", "Project was not found.")


def _task_not_found() -> Exception:
    return http_error(status.HTTP_404_NOT_FOUND, "PROJECT_TASK_NOT_FOUND", "Project task was not found.")


def _milestone_not_found() -> Exception:
    return http_error(status.HTTP_404_NOT_FOUND, "PROJECT_MILESTONE_NOT_FOUND", "Project milestone was not found.")


def _milestone_weight_invalid() -> Exception:
    return http_error(status.HTTP_409_CONFLICT, "PROJECT_MILESTONE_WEIGHT_INVALID", "Milestone weights may not exceed 100 in total.")


@router.get("", response_model=list[ProjectSummary])
def get_projects(owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> list[ProjectSummary]:
    try:
        return list_projects(settings, owner_id)
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def post_project(payload: ProjectCreate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectSummary:
    try:
        return create_project(settings, owner_id, payload)
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project_detail(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectSummary:
    try:
        return get_project(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.patch("/{project_id}", response_model=ProjectSummary)
def patch_project(project_id: UUID, payload: ProjectUpdate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectSummary:
    try:
        return update_project(settings, owner_id, project_id, payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except ProjectStatusUpdateForbiddenError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "PROJECT_STATUS_LIFECYCLE_REQUIRED", "Project status changes must use the lifecycle endpoint.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/lifecycle", response_model=ProjectLifecycle)
def get_lifecycle(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectLifecycle:
    try:
        return get_project_lifecycle(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/{project_id}/lifecycle", response_model=ProjectLifecycle)
def post_lifecycle(
    project_id: UUID,
    payload: ProjectLifecycleConfirm,
    owner_id: str = Depends(require_report_access),
    settings: Settings = Depends(get_settings),
) -> ProjectLifecycle:
    try:
        return confirm_project_lifecycle(settings, owner_id, project_id, payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except ProjectLifecycleConflictError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "PROJECT_LIFECYCLE_VERSION_CONFLICT", "Project lifecycle version does not match.") from exc
    except ProjectLifecycleRequestConflictError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "PROJECT_LIFECYCLE_REQUEST_CONFLICT", "Lifecycle request id was already used with a different payload.") from exc
    except ProjectLifecycleValidationError as exc:
        raise http_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "PROJECT_LIFECYCLE_INVALID", "Project lifecycle confirmation is invalid.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_detail(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> Response:
    try:
        delete_project(settings, owner_id, project_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/milestones", response_model=list[ProjectMilestone])
def get_milestones(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> list[ProjectMilestone]:
    try:
        return list_project_milestones(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/{project_id}/milestones", response_model=ProjectMilestone, status_code=status.HTTP_201_CREATED)
def post_milestone(project_id: UUID, payload: ProjectMilestoneCreate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectMilestone:
    try:
        return create_project_milestone(settings, owner_id, project_id, payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except ProjectMilestoneWeightError as exc:
        raise _milestone_weight_invalid() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.patch("/{project_id}/milestones/{milestone_id}", response_model=ProjectMilestone)
def patch_milestone(project_id: UUID, milestone_id: UUID, payload: ProjectMilestoneUpdate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectMilestone:
    try:
        return update_project_milestone(settings, owner_id, project_id, milestone_id, payload)
    except ProjectMilestoneNotFoundError as exc:
        raise _milestone_not_found() from exc
    except ProjectMilestoneWeightError as exc:
        raise _milestone_weight_invalid() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.delete("/{project_id}/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(project_id: UUID, milestone_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> Response:
    try:
        delete_project_milestone(settings, owner_id, project_id, milestone_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ProjectMilestoneNotFoundError as exc:
        raise _milestone_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/tasks", response_model=list[ProjectTask])
def get_tasks(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> list[ProjectTask]:
    try:
        return list_project_tasks(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/{project_id}/tasks", response_model=ProjectTask, status_code=status.HTTP_201_CREATED)
def post_task(project_id: UUID, payload: ProjectTaskCreate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectTask:
    try:
        return create_project_task(settings, owner_id, project_id, payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except ProjectMilestoneNotFoundError as exc:
        raise _milestone_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.patch("/{project_id}/tasks/{task_id}", response_model=ProjectTask)
def patch_task(project_id: UUID, task_id: UUID, payload: ProjectTaskUpdate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectTask:
    try:
        return update_project_task(settings, owner_id, project_id, task_id, payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except ProjectTaskNotFoundError as exc:
        raise _task_not_found() from exc
    except ProjectMilestoneNotFoundError as exc:
        raise _milestone_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.delete("/{project_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(project_id: UUID, task_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> Response:
    try:
        delete_project_task(settings, owner_id, project_id, task_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ProjectTaskNotFoundError as exc:
        raise _task_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.put("/{project_id}/repository", response_model=RepositorySource)
def put_repository_source(project_id: UUID, payload: RepositorySourceCreate, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> RepositorySource:
    try:
        return upsert_repository_source(settings, owner_id, project_id, payload)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except RepositorySourceConflictError as exc:
        raise http_error(status.HTTP_409_CONFLICT, "REPOSITORY_SOURCE_CONFLICT", "Repository is already linked to another project.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/repository", response_model=RepositorySource | None)
def get_project_repository(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> RepositorySource | None:
    try:
        return get_repository_source(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/commits", response_model=list[GitHubCommit])
def get_project_commits(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> list[GitHubCommit]:
    try:
        return list_project_commits(settings, owner_id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.get("/{project_id}/github-status", response_model=ProjectGitHubStatus)
def get_github_status(project_id: UUID, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> ProjectGitHubStatus:
    try:
        get_project(settings, owner_id, project_id)
        return get_project_github_status(settings, owner_id, str(project_id))
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc


@router.post("/{project_id}/github-deliveries/{delivery_id}/reprocess")
def post_reprocess_github_delivery(project_id: UUID, delivery_id: str, owner_id: str = Depends(require_report_access), settings: Settings = Depends(get_settings)) -> dict[str, str | int]:
    try:
        result = reprocess_github_delivery(settings, owner_id, str(project_id), delivery_id)
        return {"status": result.status, "reason": result.reason, "commits_stored": result.commits_stored}
    except GitHubDeliveryNotFoundError as exc:
        raise http_error(status.HTTP_404_NOT_FOUND, "GITHUB_DELIVERY_NOT_FOUND", "GitHub delivery was not found.") from exc
    except psycopg.Error as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
