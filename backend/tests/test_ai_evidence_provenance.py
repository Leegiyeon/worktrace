import json
from inspect import getsource

from app.core.config import Settings
from app.schemas.career_assets import CareerAssetAiContent
from app.services import ai_project_analyst
from app.services import career_assets as career_asset_service


def test_project_analyst_loads_and_labels_task_provenance() -> None:
    assert "source_provider, source_key" in getsource(ai_project_analyst._load_context)

    prompt = ai_project_analyst._build_prompt(
        {
            "project": {"title": "worktrace", "status": "in_progress", "objective": "", "success_criteria": ""},
            "milestones": [],
            "tasks": [
                {
                    "id": "task-1",
                    "title": "[커밋 근거] 배포 자동화 구현",
                    "status": "done",
                    "priority": "medium",
                    "due_date": None,
                    "milestone_id": None,
                    "source_provider": "derived-github",
                    "source_key": "commit-milestone:1",
                }
            ],
            "commits": [],
        }
    )

    assert "derived-github:commit-milestone:1" in prompt
    assert "커밋 근거 자동 구성 제안, 사용자 확인 완료 아님" in prompt
    assert "source_provider가 derived-github인 WBS" in ai_project_analyst.SYSTEM_PROMPT


def test_career_template_does_not_treat_derived_done_wbs_as_confirmed_completion() -> None:
    content = career_asset_service._build_career_asset_content(
        {"title": "worktrace", "status": "in_progress", "role": "PM"},
        [
            {"title": "사용자 확정 배포", "status": "done", "source_provider": None},
            {"title": "커밋 기반 자동 완료 후보", "status": "done", "source_provider": "derived-github", "source_key": "commit-milestone:1"},
        ],
        [{"title": "배포 회고"}],
        [{"title": "배포 안정화", "resume_ready": True, "evidence_work_log_ids": ["log-1"]}],
        "PM",
        [],
    )

    assert "완료 업무: 사용자 확정 배포" in content["work_summary"]
    assert "자동 구성 WBS 제안(완료 확정 아님): 커밋 기반 자동 완료 후보" in content["work_summary"]
    assert "커밋 기반 자동 완료 후보 흐름" not in content["resume_bullets"]
    assert "자동 구성 제안 1건" in content["source_summary"]


def test_preferred_outcomes_only_uses_resume_ready_items() -> None:
    outcomes = [
        {"title": "미확정 전환율", "resume_ready": False, "metric_name": "전환율", "metric_value": "42", "metric_unit": "%"},
        {"title": "확정 성과", "resume_ready": True, "after_state": "사용자 확인 완료"},
    ]

    assert career_asset_service._preferred_outcomes(outcomes) == [outcomes[1]]
    assert career_asset_service._preferred_outcomes([outcomes[0]]) == []


def test_career_ai_context_omits_unconfirmed_outcome_payloads(monkeypatch) -> None:
    calls = []

    class FakeResponses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            return type("Response", (), {"output_parsed": CareerAssetAiContent(
                work_summary="업무 로그 기준 요약",
                outcome_summary="확정 성과만 요약",
                resume_bullets="- 확정 성과 기반 bullet",
                career_description="경력기술서",
                portfolio_description="포트폴리오",
                star_answer="Situation: 기록\nTask: 정리\nAction: 연결\nResult: 확정 성과",
            )})()

    class FakeOpenAI:
        def __init__(self, api_key):
            self.responses = FakeResponses()

    monkeypatch.setattr(career_asset_service, "OpenAI", FakeOpenAI)
    fallback = career_asset_service._build_career_asset_content(
        {"title": "worktrace", "status": "in_progress", "role": "PM"}, [], [], [], "PM", []
    )

    career_asset_service._build_ai_career_asset_content(
        Settings(openai_api_key="test-key", openai_model="test-model"),
        {"title": "worktrace", "status": "in_progress", "role": "PM"},
        [{"title": "자동 WBS", "status": "done", "source_provider": "derived-github", "source_key": "commit-milestone:1"}],
        [{"title": "업무 로그"}],
        [
            {"title": "확정 성과", "resume_ready": True, "metric_value": None},
            {"title": "미확정 매출", "resume_ready": False, "metric_name": "매출", "metric_value": "100", "metric_unit": "억"},
        ],
        [{"sha": "abc", "message": "Add evidence"}],
        "PM",
        fallback,
    )

    evidence = json.loads(calls[0]["input"][1]["content"])
    assert evidence["confirmed_outcomes"] == [{"title": "확정 성과", "resume_ready": True, "metric_value": None}]
    assert evidence["pending_outcome_count"] == 1
    assert "other_outcomes" not in evidence
    assert "미확정 매출" not in calls[0]["input"][1]["content"]
    assert evidence["wbs"][0]["source_provider"] == "derived-github"
