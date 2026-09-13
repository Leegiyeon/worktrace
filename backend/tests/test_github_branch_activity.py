from types import SimpleNamespace
from uuid import uuid4

import app.services.github_branches as service


def test_branch_activity_prefers_work_branches_and_uses_compare(monkeypatch) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)

    def fake_get(settings, path, params=None):
        if path.endswith("/branches"):
            return [
                {"name": "main"},
                {"name": "dev"},
                {"name": "feat/branch-graph"},
                {"name": "docs/archive"},
            ]
        if path.endswith("/commits"):
            return []
        if "/compare/" in path:
            return {
                "ahead_by": 3,
                "behind_by": 1,
                "status": "diverged",
                "commits": [
                    {"commit": {"committer": {"date": "2026-09-13T10:00:00Z"}}}
                ],
            }
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    assert [item.name for item in result] == ["main", "dev", "feat/branch-graph"]
    assert result[1].ahead_by == 3
    assert result[1].behind_by == 1
    assert result[1].status == "diverged"
    assert sum(point.commits for point in result[1].activity) == 1
