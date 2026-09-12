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
