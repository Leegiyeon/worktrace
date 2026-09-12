from scripts.sync_github_data import REPOSITORIES, infer_milestone_key, priority, subject


def test_production_repositories_use_real_github_names() -> None:
    assert [item[0] for item in REPOSITORIES] == [
        "Leegiyeon/oncc",
        "RotemSRS/emanual",
        "Leegiyeon/worktrace",
    ]


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


def test_unknown_commit_does_not_invent_milestone() -> None:
    assert infer_milestone_key("oncc", "chore: miscellaneous cleanup") is None
    assert infer_milestone_key("unknown", "feat: anything") is None
