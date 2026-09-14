from uuid import UUID

from openai import OpenAI, OpenAIError

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.ai import ProjectAnalystResponse
from app.services.projects import ProjectNotFoundError


class AiProjectAnalystConfigurationError(Exception):
    pass


class AiProjectAnalystGenerationError(Exception):
    pass


SYSTEM_PROMPT = """당신은 개인 프로젝트의 다음 행동을 정리하는 Project Analyst다.
반드시 입력으로 제공된 프로젝트 목표, 성취 기준, 마일스톤, 계획 WBS, 최근 GitHub commit만 사용한다.
규칙:
- 제공되지 않은 사실, 일정, 테스트 결과, 장애 원인, 완료 상태를 추정하지 않는다.
- next_actions에는 아직 완료되지 않은 실제 WBS id만 사용할 수 있다.
- 우선순위는 기한 초과, 보류, 높은 우선순위, 진행 중, 예정 순으로 고려하되 프로젝트 목표와 마일스톤 성취 기준을 함께 본다.
- blockers에는 입력에서 확인 가능한 보류/기한 초과/계획 공백만 적는다.
- 완료된 WBS를 다음 행동으로 추천하지 않는다.
- GitHub commit 개수나 활동량만으로 진척 또는 완료를 판단하지 않는다.
- source_provider가 derived-github인 WBS는 커밋 근거로 자동 구성된 제안이며 사용자가 확인한 완료 근거로 간주하지 않는다.
- 근거가 부족하면 needs_attention에 무엇을 정의하거나 확인해야 하는지 명시한다.
- summary는 짧고 실무적으로 작성한다.
"""


def analyze_project(settings: Settings, owner_id: str, project_id: UUID) -> ProjectAnalystResponse:
    if not settings.openai_api_key:
        raise AiProjectAnalystConfigurationError()

    context = _load_context(settings, owner_id, project_id)
    allowed_task_ids = {str(item["id"]) for item in context["tasks"] if item["status"] != "done"}

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.responses.parse(
            model=settings.openai_model or "gpt-4o-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(context)},
            ],
            text_format=ProjectAnalystResponse,
        )
    except OpenAIError as exc:
        raise AiProjectAnalystGenerationError() from exc
    except Exception as exc:
        raise AiProjectAnalystGenerationError() from exc

    result = response.output_parsed
    if not isinstance(result, ProjectAnalystResponse):
        raise AiProjectAnalystGenerationError()

    result.next_actions = [item for item in result.next_actions if str(item.task_id) in allowed_task_ids][:5]
    result.evidence_commit_count = len(context["commits"])
    result.remaining_wbs_count = len(allowed_task_ids)

    if not context["project"]["objective"].strip() or not context["project"]["success_criteria"].strip():
        result.needs_attention = _dedupe([
            "프로젝트 목표와 성취 기준을 먼저 명확히 정의해야 합니다.",
            *result.needs_attention,
        ])[:8]

    if not context["milestones"]:
        result.needs_attention = _dedupe([
            "프로젝트 마일스톤과 가중치를 정의해야 합니다.",
            *result.needs_attention,
        ])[:8]

    if not allowed_task_ids:
        result.next_actions = []
        result.needs_attention = _dedupe([
            "진행할 계획 WBS가 없습니다. 완료 여부를 확인하거나 다음 WBS를 계획하세요.",
            *result.needs_attention,
        ])[:8]

    return result


def _load_context(settings: Settings, owner_id: str, project_id: UUID) -> dict:
    with connect(settings) as connection:
        project = connection.execute(
            """SELECT id::text, title, objective, success_criteria, status
               FROM projects WHERE owner_id=%s AND id=%s""",
            (owner_id, project_id),
        ).fetchone()
        if project is None:
            raise ProjectNotFoundError()

        milestones = connection.execute(
            """SELECT id::text, title, acceptance_criteria, weight
               FROM project_milestones
               WHERE owner_id=%s AND project_id=%s
               ORDER BY sort_order, created_at""",
            (owner_id, project_id),
        ).fetchall()
        tasks = connection.execute(
            """SELECT id::text, title, description, status, priority, due_date::text, milestone_id::text,
                      source_provider, source_key
               FROM project_tasks
               WHERE owner_id=%s AND project_id=%s AND counts_toward_progress=true
               ORDER BY due_date ASC NULLS LAST, updated_at DESC""",
            (owner_id, project_id),
        ).fetchall()
        commits = connection.execute(
            """SELECT id::text, sha, message, committed_at::text
               FROM github_commits
               WHERE owner_id=%s AND project_id=%s
               ORDER BY committed_at DESC NULLS LAST, created_at DESC LIMIT 20""",
            (owner_id, project_id),
        ).fetchall()
    return {"project": project, "milestones": milestones, "tasks": tasks, "commits": commits}


def _build_prompt(context: dict) -> str:
    project = context["project"]
    milestones = "\n".join(
        f"- id={item['id']} | {item['title']} | weight={item['weight']} | criteria={item['acceptance_criteria'] or '미정'}"
        for item in context["milestones"]
    ) or "- 없음"
    tasks = "\n".join(
        f"- id={item['id']} | {item['status']}/{item['priority']} | due={item['due_date'] or '없음'} | milestone={item['milestone_id'] or '미지정'} | "
        f"source={_task_source_label(item)} | {item['title']}"
        for item in context["tasks"]
    ) or "- 없음"
    commits = "\n".join(
        f"- id={item['id']} | {item['sha'][:8]} | {item['committed_at'] or '날짜 없음'} | {item['message']}"
        for item in context["commits"]
    ) or "- 없음"
    return f"""프로젝트: {project['title']}
상태: {project['status']}
목표: {project['objective'] or '미정'}
성취 기준: {project['success_criteria'] or '미정'}

마일스톤:
{milestones}

계획 WBS:
{tasks}

최근 GitHub Evidence:
{commits}

현재 프로젝트에서 사용자가 다음에 실제로 처리할 항목을 근거 기반으로 정리하세요."""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _task_source_label(task) -> str:
    source_provider = task.get("source_provider") or "manual"
    source_key = task.get("source_key") or ""
    if source_provider == "derived-github":
        return f"derived-github:{source_key or '-'} (커밋 근거 자동 구성 제안, 사용자 확인 완료 아님)"
    return f"{source_provider}:{source_key}" if source_key else source_provider
