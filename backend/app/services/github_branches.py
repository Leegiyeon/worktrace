from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from app.core.config import Settings
from app.schemas.projects import (
    BranchActivityPoint,
    GitHubBranchActivity,
    GitHubBranchCommitNode,
)
from app.services.projects import get_repository_source

MAX_BRANCHES = 13
MAX_HISTORY_COMMITS = 100
ACTIVITY_DAYS = 30


class GitHubBranchActivityError(Exception):
    pass


def _headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "worktrace-branch-activity",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_sync_token:
        headers["Authorization"] = f"Bearer {settings.github_sync_token}"
    return headers


def _get_json(settings: Settings, path: str, params: dict[str, str | int] | None = None):
    query = f"?{urlencode(params)}" if params else ""
    request = Request(f"https://api.github.com{path}{query}", headers=_headers(settings))
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubBranchActivityError(str(exc)) from exc


def _commit_date(commit: dict) -> str | None:
    raw = ((commit.get("commit") or {}).get("committer") or {}).get("date")
    return str(raw) if raw else None


def _branch_head_sha(branch: dict) -> str | None:
    raw = (branch.get("commit") or {}).get("sha")
    return str(raw) if raw else None


def _commit_node(commit: dict) -> GitHubBranchCommitNode | None:
    raw_sha = commit.get("sha")
    if not raw_sha:
        return None

    parents = commit.get("parents")
    parent_shas = (
        [
            str(parent["sha"])
            for parent in parents
            if isinstance(parent, dict) and parent.get("sha")
        ]
        if isinstance(parents, list)
        else []
    )
    payload = commit.get("commit") or {}
    return GitHubBranchCommitNode(
        sha=str(raw_sha),
        parents=parent_shas,
        message=str(payload.get("message") or ""),
        committed_at=_commit_date(commit),
        url=str(commit.get("html_url") or commit.get("url") or ""),
    )


def _commit_nodes(commits: list[dict]) -> list[GitHubBranchCommitNode]:
    nodes: list[GitHubBranchCommitNode] = []
    for commit in commits:
        node = _commit_node(commit)
        if node is not None:
            nodes.append(node)
    return nodes


def _activity_points(commits: list[dict]) -> list[BranchActivityPoint]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=ACTIVITY_DAYS - 1)
    counts: Counter[str] = Counter()
    for commit in commits:
        raw = _commit_date(commit)
        if not raw:
            continue
        day = raw[:10]
        if day >= start.isoformat():
            counts[day] += 1
    return [
        BranchActivityPoint(
            date=(start + timedelta(days=offset)).isoformat(),
            commits=counts[(start + timedelta(days=offset)).isoformat()],
        )
        for offset in range(ACTIVITY_DAYS)
    ]


def _selected_branch_refs(
    branches: list[dict],
    default_branch: str,
) -> tuple[list[tuple[str, str | None]], bool]:
    refs: dict[str, str | None] = {}
    for branch in branches:
        raw_name = branch.get("name")
        if raw_name:
            refs[str(raw_name)] = _branch_head_sha(branch)

    branch_list_truncated = len(refs) > MAX_BRANCHES or len(branches) >= 100
    names = sorted(refs, key=lambda name: (name != default_branch, name.lower(), name))
    return [(name, refs[name]) for name in names[:MAX_BRANCHES]], branch_list_truncated


def _default_branch_ref(
    settings: Settings,
    encoded_repo: str,
    default_branch: str,
) -> tuple[str, str | None] | None:
    branch = _get_json(
        settings,
        f"/repos/{encoded_repo}/branches/{quote(default_branch, safe='')}",
    )
    if not isinstance(branch, dict) or not branch.get("name"):
        return None
    return str(branch["name"]), _branch_head_sha(branch)


def _ensure_default_branch_ref(
    settings: Settings,
    encoded_repo: str,
    branch_refs: list[tuple[str, str | None]],
    default_branch: str,
) -> list[tuple[str, str | None]]:
    if any(name == default_branch for name, _head_sha in branch_refs):
        return branch_refs

    default_ref = _default_branch_ref(settings, encoded_repo, default_branch)
    if default_ref is None:
        return branch_refs

    return [default_ref, *branch_refs[: MAX_BRANCHES - 1]]


def _commit_history(
    settings: Settings,
    encoded_repo: str,
    head_sha: str | None,
) -> tuple[list[dict], bool]:
    if not head_sha:
        return [], False
    commits = _get_json(
        settings,
        f"/repos/{encoded_repo}/commits",
        {"sha": head_sha, "per_page": MAX_HISTORY_COMMITS},
    )
    if not isinstance(commits, list):
        return [], False
    return commits, len(commits) >= MAX_HISTORY_COMMITS


def list_project_branch_activity(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
) -> list[GitHubBranchActivity]:
    repository = get_repository_source(settings, owner_id, project_id)
    if repository is None:
        return []

    encoded_repo = "/".join(
        quote(part, safe="") for part in repository.full_name.split("/", 1)
    )
    branches = _get_json(settings, f"/repos/{encoded_repo}/branches", {"per_page": 100})
    if not isinstance(branches, list):
        raise GitHubBranchActivityError("Unexpected GitHub branches response")

    branch_refs, branch_list_truncated = _selected_branch_refs(
        branches,
        repository.default_branch,
    )
    branch_refs = _ensure_default_branch_ref(
        settings,
        encoded_repo,
        branch_refs,
        repository.default_branch,
    )
    default_head_sha = next(
        (head_sha for name, head_sha in branch_refs if name == repository.default_branch),
        None,
    )

    result: list[GitHubBranchActivity] = []
    for name, head_sha in branch_refs:
        history, history_truncated = _commit_history(settings, encoded_repo, head_sha)
        commit_nodes = _commit_nodes(history)
        if name == repository.default_branch:
            result.append(
                GitHubBranchActivity(
                    name=name,
                    is_default=True,
                    ahead_by=0,
                    behind_by=0,
                    status="default",
                    latest_commit_at=_commit_date(history[0]) if history else None,
                    activity=_activity_points(history),
                    head_sha=head_sha,
                    commits=commit_nodes,
                    history_truncated=history_truncated,
                    branch_list_truncated=branch_list_truncated,
                )
            )
            continue

        compare = (
            _get_json(
                settings,
                f"/repos/{encoded_repo}/compare/{quote(default_head_sha, safe='')}...{quote(head_sha, safe='')}",
            )
            if default_head_sha and head_sha
            else {}
        )
        compare_commits = compare.get("commits", []) if isinstance(compare, dict) else []
        if not isinstance(compare_commits, list):
            compare_commits = []
        result.append(
            GitHubBranchActivity(
                name=name,
                is_default=False,
                ahead_by=int(compare.get("ahead_by", 0)) if isinstance(compare, dict) else 0,
                behind_by=int(compare.get("behind_by", 0)) if isinstance(compare, dict) else 0,
                status=str(compare.get("status", "unknown")) if isinstance(compare, dict) else "unknown",
                latest_commit_at=_commit_date(history[0]) if history else None,
                activity=_activity_points(compare_commits),
                head_sha=head_sha,
                commits=commit_nodes,
                history_truncated=history_truncated,
                branch_list_truncated=branch_list_truncated,
            )
        )

    return result
