import sys
from uuid import uuid4

import pytest

from scripts import sync_github_data as sync

from scripts.sync_github_data import (
    REPOSITORIES,
    blueprint_for,
    generic_profile,
    infer_milestone_key,
    priority,
    repository_configs,
    subject,
)


def test_production_repositories_use_real_github_names() -> None:
    assert [item[0] for item in REPOSITORIES] == [
        "Leegiyeon/oncc",
        "RotemSRS/emanual",
        "Leegiyeon/worktrace",
    ]


def test_additional_repository_is_normalized_without_duplicate_default() -> None:
    configs = repository_configs(["Leegiyeon/hankkilog", "Leegiyeon/oncc", "bad-value"])

    assert [item[0] for item in configs][-1] == "Leegiyeon/hankkilog"
    assert [item[0] for item in configs].count("Leegiyeon/oncc") == 1
    assert all(item[0] != "bad-value" for item in configs)
    assert configs[-1][1] == "hankkilog"


def test_commit_subject_is_single_line_and_bounded() -> None:
    assert subject("feat: useful work\n\nbody") == "feat: useful work"
    assert len(subject("x" * 300)) == 240


def test_issue_priority_uses_operational_labels() -> None:
    assert priority([{"name": "security"}]) == "high"
    assert priority([{"name": "priority: low"}]) == "low"
    assert priority([]) == "medium"


def test_commit_evidence_is_classified_into_known_milestones() -> None:
    assert infer_milestone_key("oncc", "fix(ai): Assistant 조회 계획과 집계 기준 정합성 보강") == "ai-assistant"
    assert infer_milestone_key("oncc", "fix: 로그인 세션 만료 처리 및 다중 탭 인증 안정화") == "operations-reliability"
    assert infer_milestone_key("oncc", "feat: 대시보드 실시간 그래프에 최근 출동 요약 추가") == "operations-dashboard"
    assert infer_milestone_key("emanual", "feat: chunk embedding 및 vector 검색 개선") == "embedding-index"
    assert infer_milestone_key("worktrace", "feat(progress): add weighted project milestones") == "project-wbs"


def test_unknown_repository_uses_generic_milestone_classification() -> None:
    assert infer_milestone_key("hankkilog", "feat: 식사 기록 UI 구현") == "core-delivery"
    assert infer_milestone_key("hankkilog", "test: 로그인 회귀 검증") == "quality"
    assert infer_milestone_key("hankkilog", "docs: README 운영 절차 정리") == "documentation"
    assert infer_milestone_key("hankkilog", "chore: miscellaneous cleanup") is None


def test_generic_blueprint_uses_repository_description_then_readme_title() -> None:
    from_description = generic_profile({"name": "sample", "description": "팀 업무 자동화 도구"}, "# ignored")
    from_readme = generic_profile({"name": "sample", "description": None}, "# Sample Product\ncontent")

    assert "팀 업무 자동화 도구" in from_description["objective"]
    assert "Sample Product" in from_readme["objective"]
    assert sum(item[3] for item in from_description["milestones"]) == 100


def test_known_project_keeps_curated_blueprint() -> None:
    blueprint = blueprint_for("oncc", {"name": "oncc"}, "# unrelated")

    assert "관제 업무" in blueprint["objective"]
    assert any(item[0] == "ai-assistant" for item in blueprint["milestones"])


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


def test_existing_project_link_uses_project_id_without_creating_duplicate() -> None:
    project_id = str(uuid4())
    queries = []

    class Connection:
        def execute(self, query, params):
            queries.append((" ".join(query.split()), params))
            if "SELECT project_id::text FROM repository_sources" in query:
                return _Result()
            if "SELECT id::text FROM projects" in query:
                return _Result({"id": project_id})
            return _Result()

    linked, name = sync.project_for(
        Connection(), "owner", {"id": 1329341236, "full_name": "Leegiyeon/oneul-ui-gyeol", "default_branch": "main"},
        "oneul-ui-gyeol", "fallback", "developer", existing_project_id=project_id,
    )
    assert (linked, name) == (project_id, "Leegiyeon/oneul-ui-gyeol")
    assert not any("INSERT INTO projects" in query for query, _ in queries)
    assert any("INSERT INTO repository_sources" in query for query, _ in queries)


def test_preview_fetches_only_selected_window_without_database(monkeypatch, capsys) -> None:
    calls = []

    class Client:
        def get(self, path):
            calls.append(("get", path))
            return {"id": 1329341236, "full_name": "Leegiyeon/oneul-ui-gyeol", "default_branch": "main"}

        def pages(self, path, **params):
            calls.append((path, params))
            return [{"id": 1}]

    monkeypatch.setattr(sync, "GitHubClient", Client)
    monkeypatch.setattr(sync, "get_settings", lambda: object())
    monkeypatch.setattr(sync, "connect", lambda _: pytest.fail("preview must not open database"))
    monkeypatch.setattr(sys, "argv", [
        "sync_github_data.py", "--only-repository", "Leegiyeon/oneul-ui-gyeol",
        "--since", "2026-09-01", "--dry-run",
    ])
    sync.main()
    assert calls == [
        ("get", "/repos/Leegiyeon/oneul-ui-gyeol"),
        ("/repos/Leegiyeon/oneul-ui-gyeol/commits", {"sha": "main", "since": "2026-09-01T00:00:00Z"}),
        ("/repos/Leegiyeon/oneul-ui-gyeol/issues", {"state": "all", "since": "2026-09-01T00:00:00Z"}),
    ]
    assert "database_changes=0" in capsys.readouterr().out


def test_scoped_write_requires_existing_project(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", [
        "sync_github_data.py", "--only-repository", "Leegiyeon/oneul-ui-gyeol", "--since", "2026-09-01",
    ])
    with pytest.raises(SystemExit) as error:
        sync.main()
    assert error.value.code == 2
