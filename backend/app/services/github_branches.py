from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from app.core.config import Settings
from app.schemas.projects import BranchActivityPoint, GitHubBranchActivity
from app.services.projects import get_repository_source

WORK_BRANCH_PREFIXES = (
    "feat/",
    "feature/",
    "fix/",
    "hotfix/",
    "refactor/",
    "chore/",
    "release/",
)
WORK_BRANCH_NAMES = {"dev", "develop", "development"}
MAX_WORK_BRANCHES = 12
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


def _is_work_branch(name: str, default_branch: str) -> bool:
    lowered = name.lower()
    return name == default_branch or lowered in WORK_BRANCH_NAMES or lowered.startswith(WORK_BRANCH_PREFIXES)


def _commit_date(commit: dict) -> str | None:
    raw = ((commit.get("commit") or {}).get("committer") or {}).get("date")
    return str(raw) if raw else None


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
        BranchActivityPoint(date=(start + timedelta(days=offset)).isoformat(), commits=counts[(start + timedelta(days=offset)).isoformat()])
        for offset in range(ACTIVITY_DAYS)
    ]


def list_project_branch_activity(settings: Settings, owner_id: str, project_id: UUID) -> list[GitHubBranchActivity]:
    repository = get_repository_source(settings, owner_id, project_id)
    if repository is None:
        return []

    encoded_repo = "/".join(quote(part, safe="") for part in repository.full_name.split("/", 1))
    branches = _get_json(settings, f"/repos/{encoded_repo}/branches", {"per_page": 100})
    if not isinstance(branches, list):
        raise GitHubBranchActivityError("Unexpected GitHub branches response")

    names = [str(item.get("name", "")) for item in branches if item.get("name")]
    candidates = [name for name in names if _is_work_branch(name, repository.default_branch)]
    ordered = sorted(
        set(candidates),
        key=lambda name: (name != repository.default_branch, name.lower() not in WORK_BRANCH_NAMES, name.lower()),
    )[: MAX_WORK_BRANCHES + 1]

    result: list[GitHubBranchActivity] = []
    for name in ordered:
        if name == repository.default_branch:
            since = (datetime.now(timezone.utc) - timedelta(days=ACTIVITY_DAYS - 1)).isoformat()
            commits = _get_json(
                settings,
                f"/repos/{encoded_repo}/commits",
                {"sha": name, "since": since, "per_page": 100},
            )
            commits = commits if isinstance(commits, list) else []
            result.append(
                GitHubBranchActivity(
                    name=name,
                    is_default=True,
                    ahead_by=0,
                    behind_by=0,
                    status="default",
                    latest_commit_at=_commit_date(commits[0]) if commits else None,
                    activity=_activity_points(commits),
                )
            )
            continue

        compare = _get_json(
            settings,
            f"/repos/{encoded_repo}/compare/{quote(repository.default_branch, safe='')}...{quote(name, safe='')}",
        )
        commits = compare.get("commits", []) if isinstance(compare, dict) else []
        if not isinstance(commits, list):
            commits = []
        result.append(
            GitHubBranchActivity(
                name=name,
                is_default=False,
                ahead_by=int(compare.get("ahead_by", 0)) if isinstance(compare, dict) else 0,
                behind_by=int(compare.get("behind_by", 0)) if isinstance(compare, dict) else 0,
                status=str(compare.get("status", "unknown")) if isinstance(compare, dict) else "unknown",
                latest_commit_at=_commit_date(commits[-1]) if commits else None,
                activity=_activity_points(commits),
            )
        )

    return result
