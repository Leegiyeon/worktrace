from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings, get_settings
from app.db.connection import connect
from app.db.schema import init_schema

LOCAL_ENVS = {"local", "dev", "development", "test"}
SAMPLE_PREFIX = "[샘플]"
USER_PROJECT_PREFIX = "[user_project_seed]"
USER_PROJECT_GENERATION_METHOD = "user_project_seed"


@dataclass(frozen=True)
class SeedResult:
    projects: int
    tasks: int
    work_logs: int
    outcomes: int
    career_assets: int


def ensure_local_environment(settings: Settings, *, force: bool = False) -> None:
    if force:
        return
    if settings.app_env.lower() not in LOCAL_ENVS:
        raise RuntimeError(
            "seed_local.py is local/dev/test only. "
            "Set APP_ENV=local or pass --force if you intentionally seed this database."
        )


def seed(settings: Settings, *, owner_id: str | None = None, reset: bool = True, force: bool = False) -> SeedResult:
    ensure_local_environment(settings, force=force)
    init_schema(settings)
    seed_owner = owner_id or settings.default_owner_id
    today = date.today()

    with connect(settings) as connection:
        if reset:
            _delete_existing_sample_data(connection, seed_owner)

        automation_project_id = _insert_project(
            connection,
            seed_owner,
            title="[샘플] 업무 자동화 플랫폼 MVP",
            description="샘플 데이터: 파일 기반 업무 기록, 진척도, 성과, 경력 자산화 흐름을 검증하는 프로젝트입니다.",
            status="in_progress",
            role="PM/업무 자동화 기획",
        )
        reporting_project_id = _insert_project(
            connection,
            seed_owner,
            title="[샘플] 주간 리포트 운영 정리",
            description="샘플 데이터: 업무 로그 기반 주간 리포트와 다음 액션 정리 흐름을 확인하는 프로젝트입니다.",
            status="review",
            role="운영 기획/리포트 담당",
        )

        task_count = 0
        for project_id, tasks in {
            automation_project_id: [
                ("[샘플] 프로젝트/업무 CRUD 점검", "화면에서 프로젝트와 업무를 만들고 수정할 수 있는지 확인", "done", "high", today - timedelta(days=3)),
                ("[샘플] 업무 로그 입력 흐름 정리", "수행 내용, 판단, 다음 액션 필드가 경력 근거로 충분한지 확인", "in_progress", "high", today + timedelta(days=1)),
                ("[샘플] 개선 성과 카드 검증", "정량/정성 성과와 근거 업무 로그 연결 확인", "planned", "medium", today + timedelta(days=3)),
                ("[샘플] 경력 자산 문장 검토", "샘플 경력 문장이 과장 없이 생성/저장되는지 확인", "planned", "medium", today + timedelta(days=5)),
            ],
            reporting_project_id: [
                ("[샘플] 이번 주 로그 입력", "기간별 업무 로그가 리포트에 반영되는지 확인", "done", "medium", today - timedelta(days=1)),
                ("[샘플] 리포트 Markdown 복사 확인", "주간 리포트 화면에서 Markdown 출력과 복사 버튼 확인", "in_progress", "medium", today + timedelta(days=2)),
                ("[샘플] 다음 주 확인사항 정리", "잔여 업무와 지연 업무를 다음 액션으로 정리", "on_hold", "low", today + timedelta(days=7)),
            ],
        }.items():
            for title, description, status, priority, due_date in tasks:
                _insert_task(connection, seed_owner, project_id, title, description, status, priority, due_date)
                task_count += 1

        work_logs = [
            (automation_project_id, today - timedelta(days=5), "planning", "[샘플] MVP 범위 재정리", "프로젝트 진척도, 업무 로그, 성과 수치화, 경력 자산화를 v0.1 핵심 흐름으로 정리했다.", "AI 기능보다 수동 기록을 먼저 안정화하기로 결정했다.", "개인 사용자", "업무 로그와 성과 입력 화면을 확인한다.", 90, ""),
            (automation_project_id, today - timedelta(days=4), "development", "[샘플] 프로젝트 업무 상태 점검", "예정/진행/완료/보류 상태와 완료율 계산을 화면에서 확인했다.", "완료율은 완료 업무 수 / 전체 업무 수 기준으로 유지한다.", "", "잔여 업무 카운트를 대시보드에서 확인한다.", 120, ""),
            (automation_project_id, today - timedelta(days=3), "problem_solving", "[샘플] 성과 근거 필드 설계", "성과 수치를 사용자가 직접 입력하고 업무 로그를 근거로 연결하는 방식을 정리했다.", "AI가 임의 수치를 만들지 않도록 수치 입력은 사용자 확정값만 사용한다.", "", "정성 성과와 정량 성과를 분리해 등록한다.", 80, ""),
            (reporting_project_id, today - timedelta(days=2), "reporting", "[샘플] 주간 리포트 구성 확인", "프로젝트별 진행 현황과 다음 확인 사항을 Markdown으로 정리하는 흐름을 점검했다.", "리포트는 메일 발송 없이 앱 내부 생성과 복사까지만 제공한다.", "팀 리드", "다음 주 확인사항을 업무로 전환할지 검토한다.", 60, ""),
            (reporting_project_id, today - timedelta(days=1), "coordination", "[샘플] 리포트 공유 방식 협의", "리포트 Markdown을 복사해 메신저/문서에 붙여넣는 방식을 테스트했다.", "외부 서비스 연동은 v0.1 이후로 미룬다.", "운영 담당", "복사된 Markdown의 가독성을 확인한다.", 45, ""),
            (automation_project_id, today, "testing", "[샘플] 로컬 seed 데이터 검증", "샘플 프로젝트, 업무, 업무 로그, 성과, 경력 자산이 한 번에 생성되는지 확인했다.", "샘플 데이터는 제목에 [샘플]을 붙여 운영 데이터와 구분한다.", "", "대시보드에서 샘플 프로젝트가 보이는지 확인한다.", 40, ""),
        ]
        work_log_ids: list[UUID] = []
        for work_log in work_logs:
            work_log_ids.append(_insert_work_log(connection, seed_owner, *work_log))

        outcome_ids = [
            _insert_outcome(
                connection,
                seed_owner,
                automation_project_id,
                title="[샘플] 업무 상태 확인 시간 단축",
                outcome_type="quantitative",
                before_state="프로젝트별 잔여 업무를 수동으로 확인해야 했다.",
                after_state="대시보드에서 잔여 업무와 완료율을 즉시 확인할 수 있다.",
                metric_name="주간 상태 확인 소요 시간",
                metric_value="30",
                metric_unit="분 절감(샘플)",
                evidence_work_log_ids=[work_log_ids[1], work_log_ids[5]],
                resume_ready=True,
            ),
            _insert_outcome(
                connection,
                seed_owner,
                reporting_project_id,
                title="[샘플] 주간 공유 자료 정리 방식 표준화",
                outcome_type="qualitative",
                before_state="프로젝트별 진행 내용과 다음 액션이 여러 메모에 흩어져 있었다.",
                after_state="업무 로그와 리포트 Markdown으로 주간 공유 자료를 한곳에서 정리할 수 있다.",
                metric_name="",
                metric_value=None,
                metric_unit="",
                evidence_work_log_ids=[work_log_ids[3], work_log_ids[4]],
                resume_ready=True,
            ),
        ]

        _insert_career_asset(
            connection,
            seed_owner,
            automation_project_id,
            source_summary="샘플 경력 자산: 업무 로그 4건과 정량 성과 1건을 근거로 작성했습니다.",
            work_summary="프로젝트/업무 관리 흐름을 정의하고, 상태값과 완료율 계산 기준을 점검했으며, 성과 수치 입력 원칙을 정리했다.",
            outcome_summary="주간 상태 확인 소요 시간을 30분 절감할 수 있는 구조를 샘플 기준으로 확인했다. 이 수치는 샘플 데이터이며 운영 성과와 구분된다.",
            resume_bullets="- [샘플] 프로젝트별 업무 상태와 잔여 업무를 관리하는 로컬 MVP 흐름을 기획하고 검증\n- [샘플] 사용자가 확정한 수치만 성과로 반영하도록 성과 관리 기준을 정리",
            career_description="[샘플] 업무 자동화 플랫폼 MVP에서 PM/업무 자동화 기획 역할로 프로젝트 생성, 업무 상태 관리, 업무 로그, 성과 기록 흐름을 정리했다. AI가 임의 수치를 만들지 않도록 수치 성과는 사용자 확정값과 근거 업무 로그를 기준으로 관리하는 방향을 설계했다.",
            portfolio_description="[샘플] 개인 업무 관리와 경력 자산화를 연결하기 위한 로컬 MVP입니다. 프로젝트별 업무 상태, 잔여 업무, 업무 로그, 개선 성과를 한 흐름에서 확인할 수 있게 구성했습니다.",
            star_answer="Situation: [샘플] 프로젝트 진행 상황과 성과 근거가 여러 메모에 흩어져 있었습니다.\nTask: 개인 업무 관리에 필요한 최소 흐름을 한 서비스에서 확인할 수 있게 정리해야 했습니다.\nAction: 프로젝트/업무 상태, 업무 로그, 성과 입력 기준을 나누고 샘플 데이터로 흐름을 검증했습니다.\nResult: 샘플 기준으로 잔여 업무와 완료율, 성과 근거를 한 화면 흐름에서 확인할 수 있는 기반을 마련했습니다.",
        )
        _insert_career_asset(
            connection,
            seed_owner,
            reporting_project_id,
            source_summary="샘플 경력 자산: 업무 로그 2건과 정성 성과 1건을 근거로 작성했습니다.",
            work_summary="주간 리포트 구성과 Markdown 복사 흐름을 확인하고, 외부 연동 없이 앱 내부에서 공유 자료를 만들 수 있는 방식을 정리했다.",
            outcome_summary="정량 수치 없이, 흩어진 진행 내용과 다음 액션을 한 Markdown 리포트로 정리하는 정성 개선을 기록했다.",
            resume_bullets="- [샘플] 업무 로그 기반 주간 리포트 흐름을 정리하고 Markdown 공유 방식을 검증\n- [샘플] 외부 연동 없이 로컬 앱 내부에서 진행 현황과 다음 액션을 정리하는 운영 방식을 제안",
            career_description="[샘플] 주간 리포트 운영 정리 프로젝트에서 업무 로그와 프로젝트 상태를 기반으로 공유 가능한 Markdown 리포트 흐름을 검토했다. 수치가 없는 개선은 임의 수치를 만들지 않고 정성 성과로 분리해 기록했다.",
            portfolio_description="[샘플] 프로젝트별 업무 로그를 주간 리포트로 연결해 개인 업무 회고와 공유 자료 작성을 돕는 운영 흐름입니다.",
            star_answer="Situation: [샘플] 주간 진행 상황과 다음 액션이 분산되어 있었습니다.\nTask: 한 주의 업무 기록을 프로젝트별로 정리해 공유 가능한 형태로 만들어야 했습니다.\nAction: 업무 로그, 결정사항, 다음 액션을 Markdown 리포트 구조로 정리하고 복사 흐름을 확인했습니다.\nResult: 수치가 없는 개선은 정성 성과로 기록하면서도, 주간 공유 자료를 일관된 형식으로 만들 수 있는 샘플 흐름을 확보했습니다.",
        )

    return SeedResult(projects=2, tasks=task_count, work_logs=len(work_logs), outcomes=len(outcome_ids), career_assets=2)


def seed_user_projects(settings: Settings, *, owner_id: str | None = None, force: bool = False) -> SeedResult:
    """Seed local/dev user project examples without deleting or duplicating existing data."""

    ensure_local_environment(settings, force=force)
    init_schema(settings)
    seed_owner = owner_id or settings.default_owner_id

    created = SeedResult(projects=0, tasks=0, work_logs=0, outcomes=0, career_assets=0)
    with connect(settings) as connection:
        for project_seed in _user_project_seed_data(date.today()):
            project_id, project_created = _get_or_insert_project(
                connection,
                seed_owner,
                title=project_seed["title"],
                description=project_seed["description"],
                status=project_seed["status"],
                role=project_seed["role"],
            )
            created = SeedResult(
                projects=created.projects + int(project_created),
                tasks=created.tasks,
                work_logs=created.work_logs,
                outcomes=created.outcomes,
                career_assets=created.career_assets,
            )

            for task in project_seed["tasks"]:
                task_created = _insert_task_if_missing(connection, seed_owner, project_id, **task)
                created = SeedResult(
                    projects=created.projects,
                    tasks=created.tasks + int(task_created),
                    work_logs=created.work_logs,
                    outcomes=created.outcomes,
                    career_assets=created.career_assets,
                )

            work_log_ids: dict[str, UUID] = {}
            for work_log in project_seed["work_logs"]:
                work_log_id, work_log_created = _insert_work_log_if_missing(connection, seed_owner, project_id, **work_log)
                work_log_ids[work_log["title"]] = work_log_id
                created = SeedResult(
                    projects=created.projects,
                    tasks=created.tasks,
                    work_logs=created.work_logs + int(work_log_created),
                    outcomes=created.outcomes,
                    career_assets=created.career_assets,
                )

            for outcome in project_seed["outcomes"]:
                evidence_work_log_ids = [work_log_ids[title] for title in outcome["evidence_work_log_titles"] if title in work_log_ids]
                outcome_payload = {key: value for key, value in outcome.items() if key != "evidence_work_log_titles"}
                _, outcome_created = _insert_outcome_if_missing(
                    connection,
                    seed_owner,
                    project_id,
                    evidence_work_log_ids=evidence_work_log_ids,
                    **outcome_payload,
                )
                created = SeedResult(
                    projects=created.projects,
                    tasks=created.tasks,
                    work_logs=created.work_logs,
                    outcomes=created.outcomes + int(outcome_created),
                    career_assets=created.career_assets,
                )

            career_created = _insert_career_asset_if_missing(
                connection,
                seed_owner,
                project_id,
                **project_seed["career_asset"],
                generation_method=USER_PROJECT_GENERATION_METHOD,
            )
            created = SeedResult(
                projects=created.projects,
                tasks=created.tasks,
                work_logs=created.work_logs,
                outcomes=created.outcomes,
                career_assets=created.career_assets + int(career_created),
            )

    return created


def _user_project_seed_data(today: date) -> list[dict]:
    evidence_note = "추정 입력 필요"
    return [
        {
            "title": f"{USER_PROJECT_PREFIX} worktrace",
            "description": "local/dev seed · 유형: 개인 업무 자동화 플랫폼 · 태그: AI, Project Management, CareerOps, WBS · 목표: 프로젝트 진척도, 업무 로그, 성과 수치화, 경력관리",
            "status": "in_progress",
            "role": "PM/기획/개발",
            "tasks": [
                {
                    "title": "요구사항 정리",
                    "description": "v0.1 사용자 흐름과 최소 기능 범위 정리",
                    "status": "done",
                    "priority": "high",
                    "due_date": today - timedelta(days=10),
                },
                {
                    "title": "데이터 구조 설계",
                    "description": "projects, project_tasks, work_logs, project_outcomes, career_assets 구조 점검",
                    "status": "done",
                    "priority": "high",
                    "due_date": today - timedelta(days=7),
                },
                {
                    "title": "UI/UX 개선",
                    "description": "Jira식 보드·테이블·배지 중심 화면 정리",
                    "status": "in_progress",
                    "priority": "high",
                    "due_date": today + timedelta(days=2),
                },
                {
                    "title": "테스트 및 오류 수정",
                    "description": "API/seed/UI 회귀 위험 점검",
                    "status": "in_progress",
                    "priority": "medium",
                    "due_date": today + timedelta(days=4),
                },
                {
                    "title": "문서화",
                    "description": "로컬 실행과 seed 사용 방법 정리",
                    "status": "planned",
                    "priority": "medium",
                    "due_date": today + timedelta(days=6),
                },
            ],
            "work_logs": [
                {
                    "log_date": today - timedelta(days=5),
                    "work_type": "planning",
                    "title": "서비스 방향 재정의",
                    "content": "프로젝트 진척도, 업무 로그, 성과 수치화, 경력관리 흐름을 v0.1 핵심 목적으로 정리했다.",
                    "decisions": "AI 기능보다 수동 기록과 데이터 구조를 먼저 안정화한다.",
                    "collaborators": "",
                    "next_actions": "프로젝트 상세에서 업무/로그/성과/경력 흐름을 확인한다.",
                    "duration_minutes": 90,
                    "blockers": "",
                },
                {
                    "log_date": today - timedelta(days=4),
                    "work_type": "development",
                    "title": "프로젝트 업무 데이터 구조 점검",
                    "content": "업무 상태, 우선순위, 마감일, 완료율 계산 기준을 프로젝트 관리 흐름에 맞춰 확인했다.",
                    "decisions": "완료율은 완료 업무 수 / 전체 업무 수 기준으로 계산한다.",
                    "collaborators": "",
                    "next_actions": "잔여 업무와 지연 업무가 대시보드에 보이는지 점검한다.",
                    "duration_minutes": 120,
                    "blockers": "",
                },
                {
                    "log_date": today - timedelta(days=2),
                    "work_type": "testing",
                    "title": "UI 밀도 개선 검토",
                    "content": "긴 설명문을 줄이고 그래프, 표, 보드, 배지 중심으로 화면 정보를 재배치했다.",
                    "decisions": "업무 판단에 필요한 데이터만 남기고 설명문은 최소화한다.",
                    "collaborators": "",
                    "next_actions": "seed 데이터로 프로젝트 상세 탭 표시를 확인한다.",
                    "duration_minutes": 75,
                    "blockers": "",
                },
            ],
            "outcomes": [
                {
                    "title": "잔여 업무 가시성 개선 후보",
                    "outcome_type": "qualitative",
                    "before_state": "잔여 업무와 진척도를 여러 화면에서 따로 확인해야 했다.",
                    "after_state": "프로젝트별 잔여 업무와 완료율을 대시보드/상세 화면에서 함께 확인할 수 있다.",
                    "metric_name": "프로젝트별 잔여 업무 확인 시간",
                    "metric_value": None,
                    "metric_unit": evidence_note,
                    "evidence_work_log_titles": ["프로젝트 업무 데이터 구조 점검", "UI 밀도 개선 검토"],
                    "resume_ready": False,
                },
                {
                    "title": "경력 자산화 흐름 정리 후보",
                    "outcome_type": "qualitative",
                    "before_state": "업무 기록과 경력 문장이 분리되어 있었다.",
                    "after_state": "업무 로그와 성과를 기반으로 경력 문장 초안을 저장할 수 있다.",
                    "metric_name": "경력 문장 근거 연결 수준",
                    "metric_value": None,
                    "metric_unit": evidence_note,
                    "evidence_work_log_titles": ["서비스 방향 재정의"],
                    "resume_ready": False,
                },
            ],
            "career_asset": {
                "source_summary": "user_project_seed · worktrace 업무 로그와 성과 후보 기반",
                "work_summary": "개인 업무 관리용 MVP의 사용자 흐름, 데이터 구조, UI 밀도 개선 기준을 정리했다.",
                "outcome_summary": "잔여 업무와 진척도, 업무 로그, 성과 후보, 경력 문장을 한 프로젝트 흐름에서 확인할 수 있게 구성했다. 수치 성과는 추후 근거 입력이 필요하다.",
                "resume_bullets": "- 개인 업무 관리와 경력 자산화를 연결하는 worktrace MVP 흐름을 기획하고 데이터 구조를 정리\n- 업무 상태, 완료율, 업무 로그, 성과 후보, 경력 문장을 프로젝트 단위로 확인할 수 있는 구조를 설계",
                "career_description": "worktrace 프로젝트에서 개인 업무 관리와 경력 자산화를 목표로 프로젝트/업무/업무 로그/성과/경력 자산 흐름을 정리했다. 수치가 확정되지 않은 성과는 후보로 분리해 과장 없이 관리하는 기준을 적용했다.",
                "portfolio_description": "worktrace는 프로젝트 진척도, 잔여 업무, 업무 로그, 개선 성과, 경력 문장을 한 흐름에서 관리하는 개인 업무 자동화 플랫폼입니다.",
                "star_answer": "Situation: 개인 업무 기록과 경력 정리 자료가 분산되어 있었다.\nTask: 실제 수행 업무를 프로젝트 단위로 남기고 경력 자산으로 연결해야 했다.\nAction: 프로젝트, 업무, 로그, 성과, 경력 자산 구조를 나누고 v0.1 사용자 흐름을 정리했다.\nResult: 잔여 업무와 진척도, 업무 로그, 성과 후보, 경력 문장을 한 프로젝트에서 확인하는 기반을 만들었다.",
            },
        },
        {
            "title": f"{USER_PROJECT_PREFIX} OCC AI 민원 플랫폼",
            "description": "local/dev seed · 유형: 사내 업무 전산화/AI 적용 프로젝트 · 태그: OCC, 민원, 관제, AI, Dashboard · 목표: 민원 접수, 출동 관리, 안전순회 보고, 대시보드, AI 조회/요약",
            "status": "in_progress",
            "role": "업무 전산화/AI 적용 기획",
            "tasks": [
                {
                    "title": "민원 접수 흐름 요구사항 정리",
                    "description": "민원 접수부터 처리 상태 확인까지 필요한 필드와 화면 흐름 정리",
                    "status": "done",
                    "priority": "high",
                    "due_date": today - timedelta(days=9),
                },
                {
                    "title": "출동 관리 데이터 구조 설계",
                    "description": "출동 요청, 담당, 상태, 처리 결과를 연결하는 데이터 구조 검토",
                    "status": "in_progress",
                    "priority": "high",
                    "due_date": today + timedelta(days=1),
                },
                {
                    "title": "안전순회 보고 대시보드 구성",
                    "description": "보고 현황과 지연 항목을 한눈에 보는 대시보드 항목 정리",
                    "status": "in_progress",
                    "priority": "medium",
                    "due_date": today + timedelta(days=3),
                },
                {
                    "title": "AI 조회/요약 적용 방식 검토",
                    "description": "민원/출동/보고 데이터 조회와 요약에 AI를 적용할 범위 검토",
                    "status": "planned",
                    "priority": "high",
                    "due_date": today + timedelta(days=5),
                },
                {
                    "title": "테스트 및 오류 수정",
                    "description": "업무 흐름별 입력/조회/상태 변경 오류 점검",
                    "status": "planned",
                    "priority": "medium",
                    "due_date": today + timedelta(days=8),
                },
            ],
            "work_logs": [
                {
                    "log_date": today - timedelta(days=6),
                    "work_type": "planning",
                    "title": "민원/출동 업무 흐름 정리",
                    "content": "민원 접수, 출동 배정, 처리 결과, 안전순회 보고로 이어지는 업무 흐름을 정리했다.",
                    "decisions": "초기 범위는 업무 상태와 처리 이력 전산화에 둔다.",
                    "collaborators": "OCC 업무 담당자",
                    "next_actions": "출동 관리 상태값과 대시보드 지표를 확정한다.",
                    "duration_minutes": 100,
                    "blockers": "",
                },
                {
                    "log_date": today - timedelta(days=4),
                    "work_type": "research",
                    "title": "대시보드 지표 구조 검토",
                    "content": "민원 처리 상태, 출동 지연, 안전순회 보고 누락 여부를 대시보드 지표 후보로 정리했다.",
                    "decisions": "확정 수치가 없는 항목은 성과 후보로만 관리한다.",
                    "collaborators": "",
                    "next_actions": "지표별 실제 측정 기준을 업무 담당자와 확인한다.",
                    "duration_minutes": 80,
                    "blockers": "측정 기준 확정 필요",
                },
                {
                    "log_date": today - timedelta(days=2),
                    "work_type": "coordination",
                    "title": "AI 요약 적용 범위 협의",
                    "content": "민원 내용 요약, 출동 이력 조회, 안전순회 보고 요약에 AI를 적용할 수 있는 범위를 검토했다.",
                    "decisions": "업무 데이터 구조가 안정된 뒤 AI 요약을 연결한다.",
                    "collaborators": "OCC 업무 담당자",
                    "next_actions": "AI 요약에 사용할 원문 필드와 제외 정보를 정리한다.",
                    "duration_minutes": 60,
                    "blockers": "",
                },
            ],
            "outcomes": [
                {
                    "title": "민원 처리 흐름 전산화 후보",
                    "outcome_type": "qualitative",
                    "before_state": "민원 접수와 출동 처리 상태를 수동으로 확인해야 했다.",
                    "after_state": "민원, 출동, 처리 결과를 한 흐름으로 관리할 수 있는 구조를 검토했다.",
                    "metric_name": "처리 단계별 누락 확인 시간",
                    "metric_value": None,
                    "metric_unit": evidence_note,
                    "evidence_work_log_titles": ["민원/출동 업무 흐름 정리", "대시보드 지표 구조 검토"],
                    "resume_ready": False,
                },
                {
                    "title": "안전순회 보고 가시성 개선 후보",
                    "outcome_type": "qualitative",
                    "before_state": "안전순회 보고 현황과 누락 여부 확인이 분산되어 있었다.",
                    "after_state": "대시보드에서 보고 상태와 지연 항목을 확인하는 방향을 정리했다.",
                    "metric_name": "보고 누락 확인 기준",
                    "metric_value": None,
                    "metric_unit": evidence_note,
                    "evidence_work_log_titles": ["대시보드 지표 구조 검토"],
                    "resume_ready": False,
                },
            ],
            "career_asset": {
                "source_summary": "user_project_seed · OCC AI 민원 플랫폼 업무 로그와 성과 후보 기반",
                "work_summary": "민원 접수, 출동 관리, 안전순회 보고, 대시보드, AI 조회/요약 적용 범위를 업무 흐름 중심으로 정리했다.",
                "outcome_summary": "민원/출동/보고 상태를 전산화하고 대시보드로 확인하는 개선 후보를 도출했다. 수치 성과는 추후 업무 기준과 근거가 필요하다.",
                "resume_bullets": "- OCC 민원 접수와 출동 관리 흐름을 분석하고 상태 관리 및 대시보드 지표 후보를 정리\n- 민원/출동/안전순회 보고 데이터에 AI 조회·요약을 적용하기 위한 업무 범위와 데이터 기준을 검토",
                "career_description": "OCC AI 민원 플랫폼 프로젝트에서 민원 접수, 출동 관리, 안전순회 보고, 대시보드, AI 조회/요약 적용 흐름을 정리했다. 확정 수치가 없는 성과는 후보 상태로 관리하고, 실제 업무 기준 확인 후 수치화하도록 분리했다.",
                "portfolio_description": "OCC AI 민원 플랫폼은 민원 접수, 출동 상태, 안전순회 보고를 전산화하고 AI 조회/요약을 연결하기 위한 사내 업무 플랫폼 기획 프로젝트입니다.",
                "star_answer": "Situation: 민원 처리와 출동 관리 정보가 분산되어 상태 파악이 어려웠다.\nTask: 업무 흐름을 전산화하고 대시보드 및 AI 적용 범위를 정리해야 했다.\nAction: 민원/출동/보고 흐름, 상태값, 지표 후보, AI 요약 적용 범위를 업무 담당자 관점에서 정리했다.\nResult: 민원 처리 흐름 전산화와 안전순회 보고 가시성 개선을 위한 구조와 성과 후보를 도출했다.",
            },
        },
        {
            "title": f"{USER_PROJECT_PREFIX} E-manual RAG Chatbot",
            "description": "local/dev seed · 유형: 매뉴얼 기반 RAG 챗봇 · 태그: RAG, Milvus, Manual, LLM · 목표: 안전순회/운영 매뉴얼 기반 질의응답 제공",
            "status": "in_progress",
            "role": "RAG/AI 적용 기획",
            "tasks": [
                {
                    "title": "매뉴얼 문서 범위 정리",
                    "description": "안전순회/운영 매뉴얼 중 질의응답에 사용할 문서 범위 정리",
                    "status": "done",
                    "priority": "high",
                    "due_date": today - timedelta(days=8),
                },
                {
                    "title": "RAG 아키텍처 설계",
                    "description": "문서 chunking, embedding, vector search, 답변 생성 흐름 설계",
                    "status": "in_progress",
                    "priority": "high",
                    "due_date": today + timedelta(days=2),
                },
                {
                    "title": "Milvus 컬렉션/메타데이터 설계",
                    "description": "문서명, 섹션, 페이지, 출처를 검색 결과와 연결하는 구조 검토",
                    "status": "in_progress",
                    "priority": "medium",
                    "due_date": today + timedelta(days=4),
                },
                {
                    "title": "답변 출처 표시 UI 검토",
                    "description": "챗봇 답변에서 참조 매뉴얼과 위치를 표시하는 방식 정리",
                    "status": "planned",
                    "priority": "medium",
                    "due_date": today + timedelta(days=6),
                },
                {
                    "title": "테스트 및 오류 수정",
                    "description": "검색 누락, 부정확한 답변, 출처 표시 오류 검증",
                    "status": "planned",
                    "priority": "medium",
                    "due_date": today + timedelta(days=9),
                },
            ],
            "work_logs": [
                {
                    "log_date": today - timedelta(days=7),
                    "work_type": "planning",
                    "title": "안전순회/운영 매뉴얼 범위 정리",
                    "content": "RAG 챗봇에서 우선 사용할 안전순회 및 운영 매뉴얼 범위를 정리했다.",
                    "decisions": "초기 답변 범위는 검증 가능한 매뉴얼 내용으로 제한한다.",
                    "collaborators": "",
                    "next_actions": "문서 구조와 검색 메타데이터 기준을 정리한다.",
                    "duration_minutes": 70,
                    "blockers": "",
                },
                {
                    "log_date": today - timedelta(days=5),
                    "work_type": "research",
                    "title": "RAG 검색 구조 검토",
                    "content": "문서 chunking, embedding, Milvus 검색, 출처 표시 흐름을 검토했다.",
                    "decisions": "답변에는 참조 문서와 섹션을 함께 표시한다.",
                    "collaborators": "",
                    "next_actions": "chunk 메타데이터와 출처 표기 필드를 정리한다.",
                    "duration_minutes": 100,
                    "blockers": "",
                },
                {
                    "log_date": today - timedelta(days=3),
                    "work_type": "testing",
                    "title": "LLM 답변 안정성 테스트",
                    "content": "매뉴얼 근거가 없는 질문에 대해 추측 답변을 줄이는 조건을 검토했다.",
                    "decisions": "근거가 부족하면 답변 제한 또는 추가 확인 안내를 표시한다.",
                    "collaborators": "",
                    "next_actions": "출처 없는 답변을 막는 테스트 케이스를 만든다.",
                    "duration_minutes": 85,
                    "blockers": "",
                },
            ],
            "outcomes": [
                {
                    "title": "매뉴얼 질의응답 접근성 개선 후보",
                    "outcome_type": "qualitative",
                    "before_state": "필요한 매뉴얼 내용을 직접 찾아야 했다.",
                    "after_state": "질문 기반으로 관련 매뉴얼 근거를 찾아 답변하는 구조를 검토했다.",
                    "metric_name": "매뉴얼 검색 소요 시간",
                    "metric_value": None,
                    "metric_unit": evidence_note,
                    "evidence_work_log_titles": ["안전순회/운영 매뉴얼 범위 정리", "RAG 검색 구조 검토"],
                    "resume_ready": False,
                },
                {
                    "title": "답변 출처 추적성 확보 후보",
                    "outcome_type": "qualitative",
                    "before_state": "AI 답변의 근거 문서를 확인하기 어려울 수 있었다.",
                    "after_state": "답변에 문서명과 섹션 출처를 표시하는 기준을 정리했다.",
                    "metric_name": "출처 표시 기준",
                    "metric_value": None,
                    "metric_unit": evidence_note,
                    "evidence_work_log_titles": ["RAG 검색 구조 검토", "LLM 답변 안정성 테스트"],
                    "resume_ready": False,
                },
            ],
            "career_asset": {
                "source_summary": "user_project_seed · E-manual RAG Chatbot 업무 로그와 성과 후보 기반",
                "work_summary": "안전순회/운영 매뉴얼 기반 RAG 챗봇의 문서 범위, 검색 구조, 출처 표시, 답변 안정성 기준을 검토했다.",
                "outcome_summary": "매뉴얼 검색 접근성과 답변 출처 추적성 개선 후보를 도출했다. 정량 수치는 실제 사용 로그 또는 테스트 결과 입력이 필요하다.",
                "resume_bullets": "- 안전순회/운영 매뉴얼 기반 RAG 챗봇의 문서 범위, 검색 구조, 출처 표시 기준을 설계\n- Milvus 기반 검색과 LLM 답변 흐름에서 근거 없는 답변을 줄이기 위한 검증 기준을 정리",
                "career_description": "E-manual RAG Chatbot 프로젝트에서 매뉴얼 문서 범위, RAG 검색 구조, Milvus 메타데이터, 답변 출처 표시, 답변 안정성 기준을 검토했다. 수치 성과는 실제 테스트 로그가 확보된 뒤 확정하도록 후보로 관리했다.",
                "portfolio_description": "E-manual RAG Chatbot은 안전순회/운영 매뉴얼을 기반으로 질문에 답하고 참조 문서 출처를 함께 보여주는 RAG 챗봇 기획 프로젝트입니다.",
                "star_answer": "Situation: 운영 매뉴얼 내용을 빠르게 찾고 답변 근거를 확인하기 어려웠다.\nTask: 매뉴얼 기반 질의응답 구조와 출처 표시 기준을 정리해야 했다.\nAction: 문서 범위, chunking/embedding/search 흐름, Milvus 메타데이터, 출처 표시, 근거 부족 시 답변 제한 기준을 검토했다.\nResult: 매뉴얼 질의응답 접근성과 답변 출처 추적성을 높이기 위한 구조와 성과 후보를 정리했다.",
            },
        },
    ]


def _delete_existing_sample_data(connection, owner_id: str) -> None:
    sample_project_ids = connection.execute(
        "SELECT id FROM projects WHERE owner_id = %(owner_id)s AND title LIKE %(prefix)s",
        {"owner_id": owner_id, "prefix": f"{SAMPLE_PREFIX}%"},
    ).fetchall()
    project_ids = [row["id"] for row in sample_project_ids]
    if not project_ids:
        return
    connection.execute(
        "DELETE FROM career_assets WHERE owner_id = %(owner_id)s AND project_id = ANY(%(project_ids)s::uuid[])",
        {"owner_id": owner_id, "project_ids": project_ids},
    )
    connection.execute(
        "DELETE FROM project_outcomes WHERE owner_id = %(owner_id)s AND project_id = ANY(%(project_ids)s::uuid[])",
        {"owner_id": owner_id, "project_ids": project_ids},
    )
    connection.execute(
        "DELETE FROM project_tasks WHERE owner_id = %(owner_id)s AND project_id = ANY(%(project_ids)s::uuid[])",
        {"owner_id": owner_id, "project_ids": project_ids},
    )
    connection.execute(
        "DELETE FROM work_logs WHERE owner_id = %(owner_id)s AND project_id = ANY(%(project_ids)s::uuid[])",
        {"owner_id": owner_id, "project_ids": project_ids},
    )
    connection.execute(
        "DELETE FROM projects WHERE owner_id = %(owner_id)s AND id = ANY(%(project_ids)s::uuid[])",
        {"owner_id": owner_id, "project_ids": project_ids},
    )


def _insert_project(connection, owner_id: str, *, title: str, description: str, status: str, role: str) -> UUID:
    row = connection.execute(
        """
        INSERT INTO projects (owner_id, title, description, status, role)
        VALUES (%(owner_id)s, %(title)s, %(description)s, %(status)s, %(role)s)
        RETURNING id
        """,
        {"owner_id": owner_id, "title": title, "description": description, "status": status, "role": role},
    ).fetchone()
    return row["id"]


def _get_or_insert_project(connection, owner_id: str, *, title: str, description: str, status: str, role: str) -> tuple[UUID, bool]:
    row = connection.execute(
        "SELECT id FROM projects WHERE owner_id = %(owner_id)s AND title = %(title)s",
        {"owner_id": owner_id, "title": title},
    ).fetchone()
    if row is not None:
        return row["id"], False
    return _insert_project(connection, owner_id, title=title, description=description, status=status, role=role), True


def _insert_task(connection, owner_id: str, project_id: UUID, title: str, description: str, status: str, priority: str, due_date: date) -> None:
    connection.execute(
        """
        INSERT INTO project_tasks (owner_id, project_id, title, description, status, priority, due_date)
        VALUES (%(owner_id)s, %(project_id)s, %(title)s, %(description)s, %(status)s, %(priority)s, %(due_date)s)
        """,
        {
            "owner_id": owner_id,
            "project_id": project_id,
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "due_date": due_date,
        },
    )


def _insert_task_if_missing(
    connection,
    owner_id: str,
    project_id: UUID,
    *,
    title: str,
    description: str,
    status: str,
    priority: str,
    due_date: date,
) -> bool:
    row = connection.execute(
        """
        SELECT id
        FROM project_tasks
        WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s AND title = %(title)s
        """,
        {"owner_id": owner_id, "project_id": project_id, "title": title},
    ).fetchone()
    if row is not None:
        return False
    _insert_task(connection, owner_id, project_id, title, description, status, priority, due_date)
    return True


def _insert_work_log(
    connection,
    owner_id: str,
    project_id: UUID,
    log_date: date,
    work_type: str,
    title: str,
    content: str,
    decisions: str,
    collaborators: str,
    next_actions: str,
    duration_minutes: int,
    blockers: str,
) -> UUID:
    row = connection.execute(
        """
        INSERT INTO work_logs (
            owner_id, project_id, log_date, work_type, title, content, decisions,
            collaborators, next_actions, duration_minutes, blockers
        )
        VALUES (
            %(owner_id)s, %(project_id)s, %(log_date)s, %(work_type)s, %(title)s, %(content)s,
            %(decisions)s, %(collaborators)s, %(next_actions)s, %(duration_minutes)s, %(blockers)s
        )
        RETURNING id
        """,
        {
            "owner_id": owner_id,
            "project_id": project_id,
            "log_date": log_date,
            "work_type": work_type,
            "title": title,
            "content": content,
            "decisions": decisions,
            "collaborators": collaborators,
            "next_actions": next_actions,
            "duration_minutes": duration_minutes,
            "blockers": blockers,
        },
    ).fetchone()
    return row["id"]


def _insert_work_log_if_missing(
    connection,
    owner_id: str,
    project_id: UUID,
    *,
    log_date: date,
    work_type: str,
    title: str,
    content: str,
    decisions: str,
    collaborators: str,
    next_actions: str,
    duration_minutes: int,
    blockers: str,
) -> tuple[UUID, bool]:
    row = connection.execute(
        """
        SELECT id
        FROM work_logs
        WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s AND title = %(title)s
        """,
        {"owner_id": owner_id, "project_id": project_id, "title": title},
    ).fetchone()
    if row is not None:
        return row["id"], False
    return (
        _insert_work_log(
            connection,
            owner_id,
            project_id,
            log_date,
            work_type,
            title,
            content,
            decisions,
            collaborators,
            next_actions,
            duration_minutes,
            blockers,
        ),
        True,
    )


def _insert_outcome(
    connection,
    owner_id: str,
    project_id: UUID,
    *,
    title: str,
    outcome_type: str,
    before_state: str,
    after_state: str,
    metric_name: str,
    metric_value: str | None,
    metric_unit: str,
    evidence_work_log_ids: list[UUID],
    resume_ready: bool,
) -> UUID:
    row = connection.execute(
        """
        INSERT INTO project_outcomes (
            owner_id, project_id, title, outcome_type, before_state, after_state,
            metric_name, metric_value, metric_unit, evidence_work_log_ids, resume_ready
        )
        VALUES (
            %(owner_id)s, %(project_id)s, %(title)s, %(outcome_type)s, %(before_state)s,
            %(after_state)s, %(metric_name)s, %(metric_value)s, %(metric_unit)s,
            %(evidence_work_log_ids)s::uuid[], %(resume_ready)s
        )
        RETURNING id
        """,
        {
            "owner_id": owner_id,
            "project_id": project_id,
            "title": title,
            "outcome_type": outcome_type,
            "before_state": before_state,
            "after_state": after_state,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_unit": metric_unit,
            "evidence_work_log_ids": evidence_work_log_ids,
            "resume_ready": resume_ready,
        },
    ).fetchone()
    return row["id"]


def _insert_outcome_if_missing(
    connection,
    owner_id: str,
    project_id: UUID,
    *,
    title: str,
    outcome_type: str,
    before_state: str,
    after_state: str,
    metric_name: str,
    metric_value: str | None,
    metric_unit: str,
    evidence_work_log_ids: list[UUID],
    resume_ready: bool,
) -> tuple[UUID, bool]:
    row = connection.execute(
        """
        SELECT id
        FROM project_outcomes
        WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s AND title = %(title)s
        """,
        {"owner_id": owner_id, "project_id": project_id, "title": title},
    ).fetchone()
    if row is not None:
        return row["id"], False
    return (
        _insert_outcome(
            connection,
            owner_id,
            project_id,
            title=title,
            outcome_type=outcome_type,
            before_state=before_state,
            after_state=after_state,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
            evidence_work_log_ids=evidence_work_log_ids,
            resume_ready=resume_ready,
        ),
        True,
    )


def _insert_career_asset(
    connection,
    owner_id: str,
    project_id: UUID,
    *,
    source_summary: str,
    work_summary: str,
    outcome_summary: str,
    resume_bullets: str,
    career_description: str,
    portfolio_description: str,
    star_answer: str,
    generation_method: str = "seed_template",
) -> UUID:
    markdown = "\n\n".join(
        [
            "## 수행 업무 요약\n" + work_summary,
            "## 성과 요약\n" + outcome_summary,
            "## 이력서 문장\n" + resume_bullets,
            "## 경력기술서\n" + career_description,
            "## 포트폴리오 설명\n" + portfolio_description,
            "## 면접 STAR\n" + star_answer,
        ]
    )
    row = connection.execute(
        """
        INSERT INTO career_assets (
            owner_id, project_id, source_summary, work_summary, outcome_summary,
            resume_bullets, career_description, portfolio_description, star_answer,
            markdown, generation_method
        )
        VALUES (
            %(owner_id)s, %(project_id)s, %(source_summary)s, %(work_summary)s, %(outcome_summary)s,
            %(resume_bullets)s, %(career_description)s, %(portfolio_description)s, %(star_answer)s,
            %(markdown)s, %(generation_method)s
        )
        RETURNING id
        """,
        {
            "owner_id": owner_id,
            "project_id": project_id,
            "source_summary": source_summary,
            "work_summary": work_summary,
            "outcome_summary": outcome_summary,
            "resume_bullets": resume_bullets,
            "career_description": career_description,
            "portfolio_description": portfolio_description,
            "star_answer": star_answer,
            "markdown": markdown,
            "generation_method": generation_method,
        },
    ).fetchone()
    return row["id"]


def _insert_career_asset_if_missing(
    connection,
    owner_id: str,
    project_id: UUID,
    *,
    source_summary: str,
    work_summary: str,
    outcome_summary: str,
    resume_bullets: str,
    career_description: str,
    portfolio_description: str,
    star_answer: str,
    generation_method: str,
) -> bool:
    row = connection.execute(
        """
        SELECT id
        FROM career_assets
        WHERE owner_id = %(owner_id)s
          AND project_id = %(project_id)s
          AND generation_method = %(generation_method)s
        """,
        {"owner_id": owner_id, "project_id": project_id, "generation_method": generation_method},
    ).fetchone()
    if row is not None:
        return False
    _insert_career_asset(
        connection,
        owner_id,
        project_id,
        source_summary=source_summary,
        work_summary=work_summary,
        outcome_summary=outcome_summary,
        resume_bullets=resume_bullets,
        career_description=career_description,
        portfolio_description=portfolio_description,
        star_answer=star_answer,
        generation_method=generation_method,
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local-only sample worktrace data.")
    parser.add_argument("--owner-id", default=None, help="Owner id for the sample data. Defaults to DEFAULT_OWNER_ID.")
    parser.add_argument("--no-reset", action="store_true", help="Append another sample set instead of replacing existing [샘플] data.")
    parser.add_argument(
        "--user-projects",
        action="store_true",
        help="Create idempotent local/dev user project seed data without deleting existing records.",
    )
    parser.add_argument("--force", action="store_true", help="Allow seeding even when APP_ENV is not local/dev/test.")
    args = parser.parse_args()

    if args.user_projects:
        result = seed_user_projects(get_settings(), owner_id=args.owner_id, force=args.force)
        print("worktrace user project seed data created")
        marker = f"{USER_PROJECT_PREFIX} / {USER_PROJECT_GENERATION_METHOD} (local/dev seed data)"
    else:
        result = seed(get_settings(), owner_id=args.owner_id, reset=not args.no_reset, force=args.force)
        print("worktrace local sample data seeded")
        marker = f"{SAMPLE_PREFIX} (local/dev sample data)"
    print(f"- projects: {result.projects}")
    print(f"- tasks: {result.tasks}")
    print(f"- work_logs: {result.work_logs}")
    print(f"- project_outcomes: {result.outcomes}")
    print(f"- career_assets: {result.career_assets}")
    print(f"- marker: {marker}")


if __name__ == "__main__":
    main()
