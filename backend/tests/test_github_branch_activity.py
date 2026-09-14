from types import SimpleNamespace
from uuid import uuid4

import app.services.github_branches as service


def _commit(
    sha: str,
    *,
    parents: list[str] | None = None,
    date: str = "2026-09-13T10:00:00Z",
) -> dict:
    payload: dict = {
        "sha": sha,
        "commit": {"message": f"Commit {sha}", "committer": {"date": date}},
        "html_url": f"https://github.test/commit/{sha}",
    }
    if parents is not None:
        payload["parents"] = [{"sha": parent} for parent in parents]
    return payload


def test_branch_activity_includes_all_branch_names_and_uses_immutable_head_shas(
    monkeypatch,
) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)
    calls: list[tuple[str, dict | None]] = []

    branch_names = ["main", "docs/archive", "dev"] + [
        f"topic-{index:02d}" for index in range(12)
    ]
    head_by_name = {name: f"{name}-sha" for name in branch_names}

    def fake_get(settings, path, params=None):
        calls.append((path, params))
        if path.endswith("/branches"):
            return [
                {"name": name, "commit": {"sha": head_by_name[name]}}
                for name in branch_names
            ]
        if path.endswith("/commits"):
            assert params is not None
            assert params.get("since") is None
            assert params["sha"] in set(head_by_name.values())
            return [_commit(str(params["sha"]), parents=["shared-parent"])]
        if "/compare/" in path:
            assert path.startswith("/repos/owner/repo/compare/main-sha...")
            return {
                "ahead_by": 3,
                "behind_by": 1,
                "status": "diverged",
                "commits": [_commit("compare-only", parents=["main-sha"])],
            }
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    assert len(result) == 13
    assert result[0].name == "main"
    assert "docs/archive" in [item.name for item in result]
    assert result[0].head_sha == "main-sha"
    assert result[0].commits[0].sha == "main-sha"
    assert result[0].commits[0].parents == ["shared-parent"]
    assert result[0].branch_list_truncated is True
    assert result[1].ahead_by == 3
    assert result[1].behind_by == 1
    assert result[1].status == "diverged"
    assert result[1].branch_list_truncated is True
    assert sum(point.commits for point in result[1].activity) == 1
    assert all(params is None or params.get("since") is None for _path, params in calls)


def test_branch_activity_fetches_default_branch_when_first_page_omits_it(
    monkeypatch,
) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="zz-main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)
    compared_paths: list[str] = []

    def fake_get(settings, path, params=None):
        if path.endswith("/branches"):
            return [
                {
                    "name": f"branch-{index:03d}",
                    "commit": {"sha": f"head-{index:03d}"},
                }
                for index in range(100)
            ]
        if path.endswith("/branches/zz-main"):
            return {"name": "zz-main", "commit": {"sha": "default-head"}}
        if path.endswith("/commits"):
            return [_commit(str(params["sha"]), parents=[])]
        if "/compare/" in path:
            compared_paths.append(path)
            return {"ahead_by": 0, "behind_by": 0, "status": "identical", "commits": []}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    assert len(result) == 13
    assert result[0].name == "zz-main"
    assert result[0].head_sha == "default-head"
    assert all(item.branch_list_truncated is True for item in result)
    assert compared_paths
    assert all(
        path.startswith("/repos/owner/repo/compare/default-head...")
        for path in compared_paths
    )


def test_branch_activity_uses_compare_commits_for_non_default_activity(
    monkeypatch,
) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)

    def fake_get(settings, path, params=None):
        if path.endswith("/branches"):
            return [
                {"name": "main", "commit": {"sha": "base"}},
                {"name": "feature", "commit": {"sha": "feature-head"}},
            ]
        if path.endswith("/commits"):
            return [
                _commit(
                    str(params["sha"]),
                    parents=["shared"],
                    date="2026-09-13T10:00:00Z",
                ),
                _commit("shared", parents=[], date="2026-09-13T09:00:00Z"),
            ]
        if "/compare/" in path:
            return {
                "ahead_by": 1,
                "behind_by": 0,
                "status": "ahead",
                "commits": [_commit("feature-head", parents=["shared"])],
            }
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    feature = next(item for item in result if item.name == "feature")
    assert [commit.sha for commit in feature.commits] == ["feature-head", "shared"]
    assert sum(point.commits for point in feature.activity) == 1


def test_branch_activity_preserves_shared_heads_without_deduping_branch_nodes(
    monkeypatch,
) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)

    def fake_get(settings, path, params=None):
        if path.endswith("/branches"):
            return [
                {"name": "main", "commit": {"sha": "base"}},
                {"name": "feature/a", "commit": {"sha": "shared-head"}},
                {"name": "feature/b", "commit": {"sha": "shared-head"}},
            ]
        if path.endswith("/commits"):
            return [_commit(str(params["sha"]), parents=["base"])]
        if "/compare/" in path:
            return {"ahead_by": 1, "behind_by": 0, "status": "ahead", "commits": []}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    shared = [item for item in result if item.name.startswith("feature/")]
    assert [item.head_sha for item in shared] == ["shared-head", "shared-head"]
    assert [item.commits[0].sha for item in shared] == ["shared-head", "shared-head"]


def test_branch_activity_keeps_old_history_without_recent_activity(monkeypatch) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)

    def fake_get(settings, path, params=None):
        if path.endswith("/branches"):
            return [
                {"name": "main", "commit": {"sha": "base"}},
                {"name": "stale", "commit": {"sha": "old-head"}},
            ]
        if path.endswith("/commits"):
            return [_commit(str(params["sha"]), parents=[], date="2021-01-02T03:04:05Z")]
        if "/compare/" in path:
            return {"ahead_by": 0, "behind_by": 4, "status": "behind", "commits": []}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    stale = next(item for item in result if item.name == "stale")
    assert stale.latest_commit_at == "2021-01-02T03:04:05Z"
    assert stale.commits[0].sha == "old-head"
    assert sum(point.commits for point in stale.activity) == 0
    assert stale.ahead_by == 0
    assert stale.status == "behind"


def test_branch_activity_marks_truncated_history_and_handles_absent_parents(
    monkeypatch,
) -> None:
    repository = SimpleNamespace(full_name="owner/repo", default_branch="main")
    monkeypatch.setattr(service, "get_repository_source", lambda *args: repository)

    def fake_get(settings, path, params=None):
        if path.endswith("/branches"):
            return [
                {"name": "main", "commit": {"sha": "base"}},
                {"name": "release", "commit": {"sha": "release-head"}},
            ]
        if path.endswith("/commits"):
            sha = str(params["sha"])
            return [
                _commit(f"{sha}-{index}", parents=None)
                for index in range(service.MAX_HISTORY_COMMITS)
            ]
        if "/compare/" in path:
            return {"ahead_by": 2, "behind_by": 2, "status": "diverged", "commits": []}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get_json", fake_get)
    result = service.list_project_branch_activity(SimpleNamespace(), "owner", uuid4())

    release = next(item for item in result if item.name == "release")
    assert release.history_truncated is True
    assert len(release.commits) == service.MAX_HISTORY_COMMITS
    assert release.commits[0].parents == []
