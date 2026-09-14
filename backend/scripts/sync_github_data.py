from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
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

KNOWN_BLUEPRINTS = {
    "oncc": {
        "objective": "관제 업무를 하나의 운영 플랫폼으로 통합하고 실제 운영자가 안정적으로 사용할 수 있는 서비스와 신뢰 가능한 AI 업무 지원 기능을 구축·운영한다.",
        "success_criteria": "핵심 업무 전산화, 운영 대시보드 정합성, 외부 데이터 연동, AI Assistant 신뢰성, 운영 안정성, 배포·복구 체계를 모두 검증한다.",
        "milestones": (
            ("core-digitization", "핵심 업무 전산화", "민원·출동·일지 등 핵심 관제 업무가 서비스에서 정상 CRUD 및 조회 가능하다.", 25),
            ("operations-dashboard", "운영 대시보드", "실시간·기간별 주요 운영 지표가 정의된 집계 기준과 일치하고 검증된다.", 15),
            ("external-integration", "외부 데이터 연동", "Vox 등 외부 데이터가 API·Webhook으로 중복 없이 안정적으로 동기화된다.", 15),
            ("ai-assistant", "AI Assistant 신뢰성", "기간·도메인·집계 기준을 보존하고 근거 없는 응답을 차단하는 회귀 검증을 통과한다.", 20),
            ("operations-reliability", "운영 안정성", "인증·세션·rate limit·백업·모니터링·장애 대응 기준이 검증된다.", 15),
            ("delivery-recovery", "배포·복구 체계", "DEV→운영 배포와 신규 서버 이관·복구 절차가 재현 가능하게 검증된다.", 10),
        ),
    },
    "emanual": {
        "objective": "업무 매뉴얼을 검색하는 수준을 넘어 실제 업무 질문에 근거를 제시하며 신뢰성 있게 답변하는 RAG 기반 업무지원 서비스를 구축한다.",
        "success_criteria": "문서 수집·정제, 임베딩, 검색 품질, 근거 기반 답변, citation, 평가 체계, 운영화를 검증한다.",
        "milestones": (
            ("document-ingestion", "문서 수집·정제", "대상 문서를 안정적으로 수집·정제하고 동일 입력을 재처리할 수 있다.", 15),
            ("embedding-index", "Chunk·Embedding", "문서 구조와 의미를 보존하는 chunk가 embedding되어 검색 인덱스로 관리된다.", 15),
            ("retrieval-quality", "Retrieval 품질", "대표 평가 질문에서 필요한 근거가 정의된 Top-K 안에 안정적으로 포함된다.", 20),
            ("grounded-answer", "근거 기반 답변", "제공된 문서 근거만 사용하고 확인할 수 없는 내용은 확인 불가로 응답한다.", 20),
            ("citation", "Citation", "답변에서 사용자가 원문 문서와 페이지 등 근거 위치를 확인할 수 있다.", 10),
            ("evaluation", "평가 체계", "고정 평가셋으로 retrieval·answer 품질의 회귀를 반복 검증할 수 있다.", 10),
            ("operations", "운영화", "재색인·로그·장애 대응과 실제 사용자 환경에서의 실행이 검증된다.", 10),
        ),
    },
    "worktrace": {
        "objective": "매일 수행한 업무를 자동으로 증거화하고 이를 프로젝트 진행·성과·경력 자산으로 연결하는 개인 Work Intelligence 플랫폼을 구축한다.",
        "success_criteria": "프로젝트/WBS 관리, Work Capture, GitHub Evidence, Outcome, Career AI, Work Memory, Project Insight, 운영 안정성을 검증한다.",
        "milestones": (
            ("project-wbs", "프로젝트·WBS 관리", "프로젝트 목표·성취 기준·마일스톤·WBS가 연결되고 진척률이 계획 업무만으로 산정된다.", 15),
            ("work-capture", "Work Capture", "업무 기록을 빠르게 입력하고 적절한 프로젝트와 WBS에 연결할 수 있다.", 15),
            ("github-evidence", "GitHub Evidence", "commit·issue·PR을 중복 없이 증거로 축적하되 자동 완료 근거로 오용하지 않는다.", 15),
            ("outcome", "Outcome", "활동 근거에서 성과 후보를 만들고 사용자 확인 후 확정할 수 있다.", 15),
            ("career-ai", "Career AI", "실제 evidence를 근거로 resume·STAR·portfolio 문안을 생성하고 약한 근거는 초안으로 표시한다.", 15),
            ("work-memory", "Work Memory", "과거 업무를 의미 기반으로 검색하고 답변에 근거를 함께 제시한다.", 10),
            ("project-insight", "Project Insight", "blocker·우선순위·최근 활동·다음 행동을 프로젝트 단위로 분석한다.", 5),
            ("operations", "운영 안정성", "HTTPS·인증·배포·백업·복구가 실제 운영 환경에서 검증된다.", 10),
        ),
    },
}

GENERIC_BLUEPRINT = {
    "milestones": (
        ("scope", "제품·범위 정립", "README·요구사항·설계에서 핵심 목적과 범위가 설명되고 주요 변경이 그 범위와 일치한다.", 15),
        ("core-delivery", "핵심 기능 구현", "저장소의 핵심 사용자 흐름과 주요 기능이 구현되고 실제 사용 가능한 상태다.", 35),
        ("quality", "품질·검증", "테스트·회귀 검증·오류 대응으로 핵심 기능의 품질 기준을 확인할 수 있다.", 20),
        ("operations", "배포·운영 안정성", "배포·환경설정·보안·복구 절차가 재현 가능하고 운영 상태를 확인할 수 있다.", 20),
        ("documentation", "문서화·인수인계", "README·운영 문서·변경 기록이 현재 동작과 일치해 후속 작업자가 이해할 수 있다.", 10),
    ),
}

MILESTONE_KEYWORDS = {
    "oncc": (
        ("ai-assistant", ("assistant", "ai", "질의", "조회 계획", "집계 기준", "intent", "llm", "qwen", "rag")),
        ("operations-dashboard", ("dashboard", "대시보드", "실시간", "최근 출동", "공유", "그래프", "현황")),
        ("external-integration", ("vox", "webhook", "웹훅", "외부 연동", "동기화")),
        ("operations-reliability", ("session", "세션", "로그인", "인증", "rate", "보안", "만료", "cookie", "쿠키")),
        ("delivery-recovery", ("deploy", "배포", "ci/cd", "migration", "마이그레이션", "backup", "백업", "복구", "server", "서버")),
        ("core-digitization", ("민원", "출동", "일지", "incident", "dispatch", "운영 업무", "업무 관리")),
    ),
    "emanual": (
        ("document-ingestion", ("ingest", "문서", "pdf", "parser", "파서", "추출")),
        ("embedding-index", ("embedding", "임베딩", "chunk", "청크", "vector", "벡터", "milvus", "pgvector")),
        ("retrieval-quality", ("retrieval", "검색", "top-k", "rerank", "리랭크")),
        ("grounded-answer", ("ground", "근거", "answer", "답변", "hallucination", "환각", "prompt", "프롬프트")),
        ("citation", ("citation", "출처", "페이지", "근거 표시")),
        ("evaluation", ("eval", "평가", "benchmark", "회귀", "quality", "품질")),
        ("operations", ("deploy", "배포", "logging", "로그", "monitor", "운영", "재색인")),
    ),
    "worktrace": (
        ("project-wbs", ("project", "프로젝트", "wbs", "milestone", "마일스톤", "progress", "진척")),
        ("work-capture", ("work log", "work-log", "업무 로그", "capture", "기록")),
        ("github-evidence", ("github", "commit", "커밋", "webhook", "evidence", "근거", "repository", "repo")),
        ("outcome", ("outcome", "성과")),
        ("career-ai", ("career", "resume", "star", "portfolio", "경력", "이력서", "포트폴리오")),
        ("work-memory", ("memory", "rag", "vector", "embedding", "검색", "기억")),
        ("project-insight", ("insight", "blocker", "priority", "우선순위", "분석")),
        ("operations", ("deploy", "배포", "oracle", "https", "auth", "인증", "backup", "복구", "docker")),
    ),
    "__generic__": (
        ("documentation", ("docs", "readme", "documentation", "문서", "manual", "handoff", "spec")),
        ("quality", ("test", "qa", "verify", "regression", "회귀", "bug", "fix", "검증")),
        ("operations", ("deploy", "release", "docker", "ci", "cd", "auth", "security", "backup", "migration", "운영", "배포", "보안")),
        ("scope", ("plan", "planning", "design", "architecture", "요구사항", "설계", "기획")),
        ("core-delivery", ("feat", "feature", "api", "ui", "frontend", "backend", "implement", "구현", "기능")),
    ),
}


class GitHubClient:
    def __init__(self) -> None:
        self.headers = {"Accept": "application/vnd.github+json", "User-Agent": "worktrace-sync"}
        if token := os.environ.get("GITHUB_SYNC_TOKEN"):
            self.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str) -> dict:
        with urlopen(Request(f"https://api.github.com{path}", headers=self.headers), timeout=30) as response:
            return json.load(response)

    def try_get(self, path: str) -> dict | None:
        try:
            return self.get(path)
        except HTTPError as exc:
            if exc.code in {403, 404}:
                return None
            raise

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

    def readme(self, full_name: str) -> str:
        payload = self.try_get(f"/repos/{full_name}/readme")
        if not payload or payload.get("encoding") != "base64" or not payload.get("content"):
            return ""
        try:
            return base64.b64decode(str(payload["content"])).decode("utf-8", errors="replace")[:12000]
        except (ValueError, TypeError):
            return ""


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


def repository_configs(extra_repositories: list[str] | None = None) -> tuple[tuple[str, str, str, str], ...]:
    configured = list(REPOSITORIES)
    extra = list(extra_repositories or [])
    env_value = os.environ.get("WORKTRACE_GITHUB_REPOSITORIES", "")
    extra.extend(value.strip() for value in env_value.split(",") if value.strip())
    known = {item[0].lower() for item in configured}
    for full_name in extra:
        normalized = full_name.strip().strip("/")
        if not normalized or "/" not in normalized or normalized.lower() in known:
            continue
        repo_name = normalized.split("/", 1)[1]
        configured.append((normalized, repo_name, "GitHub 저장소 기반 프로젝트", "기획/개발/운영"))
        known.add(normalized.lower())
    return tuple(configured)


def generic_profile(metadata: dict, readme: str) -> dict:
    description = str(metadata.get("description") or "").strip()
    readme_title = ""
    for line in readme.splitlines():
        normalized = line.strip().lstrip("#").strip()
        if normalized:
            readme_title = normalized[:180]
            break
    subject_text = description or readme_title or str(metadata.get("name") or metadata.get("full_name") or "GitHub 프로젝트")
    return {
        "objective": f"{subject_text}의 핵심 사용자 가치를 안정적으로 제공하고 지속적으로 개선할 수 있는 운영 가능한 상태를 만든다.",
        "success_criteria": "핵심 범위 정의, 주요 기능 구현, 품질 검증, 배포·운영 안정성, 문서화 기준을 충족한다.",
        "milestones": GENERIC_BLUEPRINT["milestones"],
    }


def blueprint_for(project_title: str, metadata: dict, readme: str) -> dict:
    return KNOWN_BLUEPRINTS.get(project_title.lower()) or generic_profile(metadata, readme)


def ensure_project_blueprint(connection, owner_id: str, project_id: str, project_title: str, metadata: dict, readme: str) -> None:
    blueprint = blueprint_for(project_title, metadata, readme)
    connection.execute(
        """UPDATE projects
           SET objective=CASE WHEN btrim(COALESCE(objective,''))='' THEN %s ELSE objective END,
               success_criteria=CASE WHEN btrim(COALESCE(success_criteria,''))='' THEN %s ELSE success_criteria END,
               updated_at=now()
           WHERE owner_id=%s AND id=%s""",
        (blueprint["objective"], blueprint["success_criteria"], owner_id, project_id),
    )
    for sort_index, (key, title, criteria, weight) in enumerate(blueprint["milestones"], start=1):
        connection.execute(
            """INSERT INTO project_milestones(owner_id,project_id,milestone_key,title,acceptance_criteria,weight,sort_order)
               VALUES(%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(owner_id,project_id,milestone_key) DO NOTHING""",
            (owner_id, project_id, key, title, criteria, weight, sort_index * 10),
        )


def infer_milestone_key(project_title: str, text: str) -> str | None:
    normalized = text.lower()
    rules = MILESTONE_KEYWORDS.get(project_title.lower()) or MILESTONE_KEYWORDS["__generic__"]
    for milestone_key, keywords in rules:
        if any(keyword.lower() in normalized for keyword in keywords):
            return milestone_key
    return None


def milestone_id_for(connection, owner_id: str, project_id: str, project_title: str, text: str) -> str | None:
    milestone_key = infer_milestone_key(project_title, text)
    if not milestone_key:
        return None
    row = connection.execute(
        "SELECT id::text FROM project_milestones WHERE owner_id=%s AND project_id=%s AND milestone_key=%s",
        (owner_id, project_id, milestone_key),
    ).fetchone()
    return row["id"] if row else None


def project_for(connection, owner_id: str, metadata: dict, title: str, fallback: str, role: str, readme: str = "") -> tuple[str, str]:
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
        "UPDATE projects SET title=%s, description=%s, role=%s, updated_at=now() WHERE owner_id=%s AND id=%s",
        (title, metadata.get("description") or fallback, role, owner_id, project_id),
    )
    connection.execute(
        """INSERT INTO repository_sources(owner_id,project_id,repository_id,full_name,default_branch)
           VALUES(%s,%s,%s,%s,%s)
           ON CONFLICT(owner_id,provider,repository_id) DO UPDATE SET project_id=excluded.project_id,
             full_name=excluded.full_name, default_branch=excluded.default_branch, updated_at=now()""",
        (owner_id, project_id, metadata["id"], metadata["full_name"], metadata.get("default_branch") or "main"),
    )
    ensure_project_blueprint(connection, owner_id, project_id, title, metadata, readme)
    return project_id, metadata["full_name"]


def sync_repo(connection, client: GitHubClient, owner_id: str, config: tuple[str, str, str, str], max_tasks: int) -> tuple[int, int, int]:
    requested, title, fallback, role = config
    metadata = client.get(f"/repos/{requested}")
    readme = client.readme(str(metadata.get("full_name") or requested))
    project_id, full_name = project_for(connection, owner_id, metadata, title, fallback, role, readme)
    source_id = connection.execute(
        "SELECT id::text FROM repository_sources WHERE owner_id=%s AND repository_id=%s", (owner_id, metadata["id"])
    ).fetchone()["id"]
    commits = client.pages(f"/repos/{full_name}/commits", sha=metadata.get("default_branch") or "main")
    by_day: dict[str, list[str]] = defaultdict(list)
    for item in commits:
        commit = item.get("commit") or {}
        author, committer = commit.get("author") or {}, commit.get("committer") or {}
        committed_at = committer.get("date") or author.get("date")
        message = commit.get("message") or ""
        commit_title = subject(message)
        commit_row = connection.execute(
            """INSERT INTO github_commits(repository_source_id,project_id,owner_id,sha,message,author_name,author_email,committed_at,url)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(owner_id,repository_source_id,sha) DO UPDATE SET message=excluded.message,
                 committed_at=excluded.committed_at,url=excluded.url
               RETURNING id::text""",
            (source_id, project_id, owner_id, item["sha"], message, author.get("name") or "",
             author.get("email") or "", committed_at, item.get("html_url") or ""),
        ).fetchone()
        milestone_id = milestone_id_for(connection, owner_id, project_id, title, message)
        if milestone_id:
            connection.execute(
                """INSERT INTO project_milestone_evidence(owner_id,project_id,milestone_id,github_commit_id,confidence)
                   VALUES(%s,%s,%s,%s,'keyword')
                   ON CONFLICT(owner_id,milestone_id,github_commit_id) DO NOTHING""",
                (owner_id, project_id, milestone_id, commit_row["id"]),
            )
        if committed_at:
            by_day[committed_at[:10]].append(commit_title)

    connection.execute(
        "DELETE FROM project_tasks WHERE owner_id=%s AND project_id=%s AND source_provider='github' AND source_key LIKE 'commit:%%'",
        (owner_id, project_id),
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
        issue_title = str(issue.get("title") or "")
        milestone_id = milestone_id_for(connection, owner_id, project_id, title, issue_title)
        counts_toward_progress = kind == "issue"
        connection.execute(
            """INSERT INTO project_tasks(owner_id,project_id,title,description,status,priority,source_provider,source_key,milestone_id,counts_toward_progress)
               VALUES(%s,%s,%s,%s,%s,%s,'github',%s,%s,%s)
               ON CONFLICT(owner_id,source_provider,source_key) WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
               DO UPDATE SET title=excluded.title,description=excluded.description,status=excluded.status,
                 priority=excluded.priority,milestone_id=excluded.milestone_id,
                 counts_toward_progress=excluded.counts_toward_progress,updated_at=now()""",
            (owner_id, project_id, f"{prefix} #{issue['number']} · {issue_title[:200]}", issue.get("html_url") or "",
             "done" if issue.get("state") == "closed" else "in_progress", priority(issue.get("labels") or []),
             f"{kind}:{full_name}:{issue['number']}", milestone_id, counts_toward_progress),
        )
    return len(commits), len(issues), len(by_day)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize real GitHub evidence into Worktrace.")
    parser.add_argument("--cleanup-samples", action="store_true")
    parser.add_argument("--repository", action="append", default=[], help="Additional owner/repository to synchronize and blueprint automatically.")
    parser.add_argument("--max-commit-tasks", type=int, default=100, help="Deprecated compatibility option; commits are evidence only.")
    args = parser.parse_args()
    settings, client = get_settings(), GitHubClient()
    totals = [0, 0, 0]
    with connect(settings) as connection:
        if args.cleanup_samples:
            connection.execute(
                "DELETE FROM projects WHERE owner_id=%s AND (title LIKE '[샘플]%%' OR title LIKE '[user_project_seed]%%')",
                (settings.default_owner_id,),
            )
        for config in repository_configs(args.repository):
            counts = sync_repo(connection, client, settings.default_owner_id, config, args.max_commit_tasks)
            totals = [left + right for left, right in zip(totals, counts)]
    print(f"GitHub sync complete: commits={totals[0]}, issue_pr_tasks={totals[1]}, work_logs={totals[2]}")


if __name__ == "__main__":
    main()
