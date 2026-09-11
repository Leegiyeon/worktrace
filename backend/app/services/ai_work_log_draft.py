import re
from uuid import UUID

from openai import OpenAI, OpenAIError

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.ai import WorkLogDraftRequest, WorkLogDraftResponse


class AiConfigurationError(Exception):
    pass


class AiDraftGenerationError(Exception):
    pass


class AiDraftProjectNotFoundError(Exception):
    pass


SYSTEM_PROMPT = """한국어 업무 메모를 worktrace 업무 로그 초안 JSON으로 정리한다.
규칙:
- 출력은 지정된 스키마만 따른다.
- 저장하지 않는다. 사용자가 검토 후 별도 저장한다.
- raw_text에 없는 소요 시간은 duration_minutes=0으로 둔다.
- raw_text에 없는 협업자, 결정사항, 블로커는 빈 문자열로 둔다.
- 수치/성과/metric/outcome은 만들지 않는다.
- 자연스러운 업무 로그 문장으로 짧고 실무적으로 정리한다.
- work_type은 planning, meeting, research, deliverable, development, testing, reporting, coordination, problem_solving, other 중 하나다.
"""


def generate_work_log_draft(settings: Settings, owner_id: str, payload: WorkLogDraftRequest) -> WorkLogDraftResponse:
    if payload.project_id is not None:
        _ensure_project_owned(settings, owner_id, payload.project_id)

    if not settings.openai_api_key:
        raise AiConfigurationError()

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.responses.parse(
            model=settings.openai_model or "gpt-4o-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(payload.raw_text)},
            ],
            text_format=WorkLogDraftResponse,
        )
    except OpenAIError as exc:
        raise AiDraftGenerationError() from exc
    except Exception as exc:  # SDK parsing/config failures must not leak raw messages.
        raise AiDraftGenerationError() from exc

    draft = response.output_parsed
    if not isinstance(draft, WorkLogDraftResponse):
        raise AiDraftGenerationError()

    if not _mentions_duration(payload.raw_text):
        draft.duration_minutes = 0
    return draft


def _ensure_project_owned(settings: Settings, owner_id: str, project_id: UUID) -> None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT id FROM projects WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
    if row is None:
        raise AiDraftProjectNotFoundError()


def _user_prompt(raw_text: str) -> str:
    return "다음 한국어 업무 메모를 업무 로그 초안으로 정리하세요.\n\n메모:\n" + raw_text


def _mentions_duration(raw_text: str) -> bool:
    return bool(re.search(r"\d+\s*(분|시간|hr|hour|hours|m|min|minutes)", raw_text, re.IGNORECASE))
