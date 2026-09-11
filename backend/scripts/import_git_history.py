import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db.connection import connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import an existing main-branch Git history as project evidence.")
    parser.add_argument("--project-title", required=True)
    parser.add_argument("--repo-path", required=True, type=Path)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    return parser.parse_args()


def read_commits(repo_path: Path) -> list[dict[str, str]]:
    output = subprocess.run(
        ["git", "-C", str(repo_path), "log", "main", "--format=%H%x09%an%x09%ae%x09%aI%x09%s"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    commits = []
    for line in output.splitlines():
        sha, author_name, author_email, committed_at, message = line.split("\t", 4)
        commits.append({
            "sha": sha,
            "author_name": author_name,
            "author_email": author_email,
            "committed_at": committed_at,
            "message": message,
        })
    return commits


def main() -> None:
    args = parse_args()
    settings = get_settings()
    commits = read_commits(args.repo_path)
    with connect(settings) as connection:
        project = connection.execute(
            "SELECT id::text FROM projects WHERE owner_id = %(owner_id)s AND title = %(title)s",
            {"owner_id": settings.default_owner_id, "title": args.project_title},
        ).fetchone()
        if project is None:
            raise SystemExit(f"Project not found: {args.project_title}")
        source = connection.execute(
            """
            INSERT INTO repository_sources (owner_id, project_id, repository_id, full_name, default_branch)
            VALUES (%(owner_id)s, %(project_id)s, %(repository_id)s, %(full_name)s, 'main')
            ON CONFLICT (owner_id, provider, repository_id) DO UPDATE
            SET project_id = EXCLUDED.project_id, full_name = EXCLUDED.full_name,
                default_branch = 'main', updated_at = now()
            RETURNING id::text
            """,
            {
                "owner_id": settings.default_owner_id,
                "project_id": project["id"],
                "repository_id": args.repository_id,
                "full_name": args.full_name,
            },
        ).fetchone()
        stored = 0
        for commit in commits:
            result = connection.execute(
                """
                INSERT INTO github_commits (
                    repository_source_id, project_id, owner_id, sha, message, author_name,
                    author_email, committed_at, url
                ) VALUES (
                    %(source_id)s, %(project_id)s, %(owner_id)s, %(sha)s, %(message)s,
                    %(author_name)s, %(author_email)s, %(committed_at)s, %(url)s
                )
                ON CONFLICT (owner_id, repository_source_id, sha) DO NOTHING
                """,
                {
                    **commit,
                    "source_id": source["id"],
                    "project_id": project["id"],
                    "owner_id": settings.default_owner_id,
                    "url": f"https://github.com/{args.full_name}/commit/{commit['sha']}",
                },
            )
            stored += max(result.rowcount, 0)
    print(f"{args.project_title}: {stored} imported, {len(commits)} total")


if __name__ == "__main__":
    main()
