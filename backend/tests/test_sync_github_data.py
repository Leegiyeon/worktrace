from scripts.sync_github_data import REPOSITORIES, priority, subject


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
