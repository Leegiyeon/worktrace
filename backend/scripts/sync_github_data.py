from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db.connection import connect

REPOSITORIES = (
    ("Leegiyeon/oncc", "oncc", "OCC 업무 시스템", "기획/개발/운영"),
    ("RotemSRS/emanual", "emanual", "E-manual RAG 서비스", "기획/개발"),
    ("Leegiyeon/worktrace", "worktrace", "GitHub 근거 기반 프로젝트·업무·경력 관리 서비스", "기획/개발/운영"),
)


class GitHubClient:
    def __init__(self) -> None:
        self.headers = {"Accept": "application/vnd.github+json", "User-Agent": "worktrace-sync"}
        if token := os.environ.get("GITHUB_SYNC_TOKEN"):
            self.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str) -> dict:
        with urlopen(Request(f"https://api.github.com{path}", headers=self.headers), timeout=30) as response:
            return json.load(response)

    def pages(self, path: str, **params) -> list[dict]:
        items = []
        for page in range(1, 101):
            query = urlencode({**params, "per_page": 100, "page": page})
            batch = self.get(f"{path}?{query}")
            if not isinstance(batch, list):
                raise RuntimeError(f"Unexpected GitHub response for {path}")
            items.extend(batch)
            if len(batch) < 100:
                break
        return items


def subject(message: str) -> str:
    lines = message.splitlines()
    return (((lines[0] if lines else "").strip()) or "제목 없는 커밋")[:240]


def priority(labels: list[dict]) -> str:
    names = {str(label.get("name", "")).lower() for label in labels}
    if names & {"critical", "high", "priority: high", "bug", "security"}:
        return "high"
    if names & {"low", "priority: low"}:
        return "low"
    return "medium"


def project_for(connection, owner_id: str, metadata: dict, title: str, fallback: str, role: str) -> tuple[str, str]:
    source = connection.execute(
        "SELECT project_id::text FROM repository_sources WHERE owner_id=%s AND repository_id=%s",
        (owner_id, metadata["id"]),
    ).fetchone()
    if source:
        project_id = source["project_id"]
    else:
        project = connection.execute(
            "SELECT id::text FROM projects WHERE owner_id=%s AND lower(title)=lower(%s) ORDER BY updated_at DESC LIMIT 1",
            (owner_id, title),
        ).fetchone()
        project_id = project["id"] if project else connection.execute(
            "INSERT INTO projects(owner_id,title,description,status,role) VALUES(%s,%s,%s,'in_progress',%s) RETURNING id::text",
            (owner_id, title, metadata.get("description") or fallback, role),
        ).fetchone()["id"]
    connection.execute(
        "UPDATE projects SET title=%s, description=%s, status='in_progress', role=%s, updated_at=now() WHERE owner_id=%s AND id=%s",
        (title, metadata.get("description") or fallback, role, owner_id, project_id),
    )
    connection.execute(
        """INSERT INTO repository_sources(owner_id,project_id,repository_id,full_name,default_branch)
           VALUES(%s,%s,%s,%s,%s)
           ON CONFLICT(owner_id,provider,repository_id) DO UPDATE SET project_id=excluded.project_id,
             full_name=excluded.full_name, default_branch=excluded.default_branch, updated_at=now()""",
        (owner_id, project_id, metadata["id"], metadata["full_name"], metadata.get("default_branch") or "main"),
    )
    return project_id, metadata["full_name"]


def sync_repo(connection, client: GitHubClient, owner_id: str, config: tuple[str, str, str, str], max_tasks: int) -> tuple[int, int, int]:
    requested, title, fallback, role = config
    metadata = client.get(f"/repos/{requested}")
    project_id, full_name = project_for(connection, owner_id, metadata, title, fallback, role)
    source_id = connection.execute(
        "SELECT id::text FROM repository_sources WHERE owner_id=%s AND repository_id=%s", (owner_id, metadata["id"])
    ).fetchone()["id"]
    commits = client.pages(f"/repos/{full_name}/commits", sha=metadata.get("default_branch") or "main")
    by_day: dict[str, list[str]] = defaultdict(list)
    for index, item in enumerate(commits):
        commit = item.get("commit") or {}
        author, committer = commit.get("author") or {}, commit.get("committer") or {}
        committed_at = committer.get("date") or author.get("date")
        title = subject(commit.get("message") or "")
        connection.execute(
            """INSERT INTO github_commits(repository_source_id,project_id,owner_id,sha,message,author_name,author_email,committed_at,url)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(owner_id,repository_source_id,sha) DO UPDATE SET message=excluded.message,
                 committed_at=excluded.committed_at,url=excluded.url""",
            (source_id, project_id, owner_id, item["sha"], commit.get("message") or "", author.get("name") or "",
             author.get("email") or "", committed_at, item.get("html_url") or ""),
        )
        if committed_at:
            by_day[committed_at[:10]].append(title)
        if index < max_tasks:
            connection.execute(
                """INSERT INTO project_tasks(owner_id,project_id,title,description,status,priority,source_provider,source_key)
                   VALUES(%s,%s,%s,%s,'done','medium','github',%s)
                   ON CONFLICT(owner_id,source_provider,source_key) WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
                   DO UPDATE SET title=excluded.title,description=excluded.description,status='done',updated_at=now()""",
                (owner_id, project_id, title, f"main 커밋 {item['sha'][:7]} · {item.get('html_url') or ''}",
                 f"commit:{source_id}:{item['sha']}"),
            )
    for day, titles in by_day.items():
        content = "\n".join(f"- {value}" for value in titles[:20])
        if len(titles) > 20:
            content += f"\n- 외 {len(titles) - 20}개 커밋"
        connection.execute(
            """INSERT INTO work_logs(owner_id,project_id,log_date,work_type,title,content,decisions,next_actions,duration_minutes,source_provider,source_key)
               VALUES(%s,%s,%s,'development',%s,%s,'main 브랜치 커밋 근거 자동 동기화','후속 WBS와 성과 근거를 검토한다.',0,'github',%s)
               ON CONFLICT(owner_id,source_provider,source_key) WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
               DO UPDATE SET title=excluded.title,content=excluded.content,updated_at=now()""",
            (owner_id, project_id, date.fromisoformat(day), f"GitHub 작업 · {len(titles)}개 커밋", content, f"day:{source_id}:{day}"),
        )
    issues = client.pages(f"/repos/{full_name}/issues", state="all")
    for issue in issues:
        kind = "pr" if issue.get("pull_request") else "issue"
        prefix = "PR" if kind == "pr" else "Issue"
        connection.execute(
            """INSERT INTO project_tasks(owner_id,project_id,title,description,status,priority,source_provider,source_key)
               VALUES(%s,%s,%s,%s,%s,%s,'github',%s)
               ON CONFLICT(owner_id,source_provider,source_key) WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
               DO UPDATE SET title=excluded.title,description=excluded.description,status=excluded.status,
                 priority=excluded.priority,updated_at=now()""",
            (owner_id, project_id, f"{prefix} #{issue['number']} · {issue['title'][:200]}", issue.get("html_url") or "",
             "done" if issue.get("state") == "closed" else "in_progress", priority(issue.get("labels") or []),
             f"{kind}:{full_name}:{issue['number']}"),
        )
    return len(commits), len(issues), len(by_day)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize real GitHub evidence into Worktrace.")
    parser.add_argument("--cleanup-samples", action="store_true")
    parser.add_argument("--max-commit-tasks", type=int, default=100)
    args = parser.parse_args()
    settings, client = get_settings(), GitHubClient()
    totals = [0, 0, 0]
    with connect(settings) as connection:
        if args.cleanup_samples:
            connection.execute(
                "DELETE FROM projects WHERE owner_id=%s AND (title LIKE '[샘플]%%' OR title LIKE '[user_project_seed]%%')",
                (settings.default_owner_id,),
            )
        for config in REPOSITORIES:
            counts = sync_repo(connection, client, settings.default_owner_id, config, args.max_commit_tasks)
            totals = [left + right for left, right in zip(totals, counts)]
    print(f"GitHub sync complete: commits={totals[0]}, issue_pr_tasks={totals[1]}, work_logs={totals[2]}")


if __name__ == "__main__":
    main()
