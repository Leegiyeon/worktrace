from datetime import date

import psycopg
from fastapi.testclient import TestClient

from app.api import reports
from app.core.config import Settings
from app.main import app
from app.services.weekly_report import (
    DocumentRecord,
    ExtractedRecord,
    ProjectRecord,
    WeeklyReportDataset,
    build_weekly_report_response,
)


def sample_dataset() -> WeeklyReportDataset:
    return WeeklyReportDataset(
        projects=[
            ProjectRecord(
                id="00000000-0000-0000-0000-000000000001",
                title="사업 자동화 정리",
                description="문서 기반 업무 흐름 정리",
                status="in_progress",
                role="PM",
                updated_at="2026-06-01 09:00:00+00",
            )
        ],
        documents=[
            DocumentRecord(
                id="00000000-0000-0000-0000-000000000011",
                project_id="00000000-0000-0000-0000-000000000001",
                filename="kickoff.md",
                summary="킥오프 논의와 범위가 정리됨",
                document_type="meeting_note",
                analysis_status="completed",
                updated_at="2026-06-01 10:00:00+00",
            )
        ],
        extracted_items=[
            ExtractedRecord(
                id="00000000-0000-0000-0000-000000000021",
                project_id="00000000-0000-0000-0000-000000000001",
                item_type="task",
                title="요구사항 재확인",
                content="범위 변경 여부를 확인한다.",
                status="open",
                due_date="2026-06-08",
                updated_at="2026-06-01 11:00:00+00",
            ),
            ExtractedRecord(
                id="00000000-0000-0000-0000-000000000022",
                project_id="00000000-0000-0000-0000-000000000001",
                item_type="decision",
                title="MVP 우선",
                content="메일 전송은 제외한다.",
                status="confirmed",
                due_date=None,
                updated_at="2026-06-01 11:30:00+00",
            ),
            ExtractedRecord(
                id="00000000-0000-0000-0000-000000000023",
                project_id="00000000-0000-0000-0000-000000000001",
                item_type="risk",
                title="데이터 부족",
                content="근거가 없는 성과는 만들지 않는다.",
                status="open",
                due_date=None,
                updated_at="2026-06-01 12:00:00+00",
            ),
        ],
    )


def test_build_weekly_report_uses_stored_records_only():
    response = build_weekly_report_response(sample_dataset(), date(2026, 6, 1), date(2026, 6, 7))

    assert "# 주간 업무 리포트 (2026-06-01 ~ 2026-06-07)" in response.markdown
    assert "사업 자동화 정리" in response.markdown
    assert "요구사항 재확인" in response.markdown
    assert "MVP 우선" in response.markdown
    assert "데이터 부족" in response.markdown
    assert "경력 기록용 요약" not in response.markdown
    assert "매출" not in response.markdown


def test_weekly_report_api_returns_markdown(monkeypatch):
    def fake_fetch_weekly_report_dataset(settings, start_date, end_date, owner_id):
        assert owner_id == "local-owner"
        return sample_dataset()

    monkeypatch.setattr(reports, "fetch_weekly_report_dataset", fake_fetch_weekly_report_dataset)
    client = TestClient(app)

    response = client.post(
        "/reports/weekly",
        headers={
            "X-Worktrace-Owner-Id": "local-owner",
            "X-Worktrace-Report-Token": "dev-only-report-token",
        },
        json={"start_date": "2026-06-01", "end_date": "2026-06-07"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"] == "2026-06-01"
    assert body["end_date"] == "2026-06-07"
    assert "Markdown" not in body["markdown"]
    assert body["projects"][0]["title"] == "사업 자동화 정리"


def test_weekly_report_rejects_invalid_period():
    client = TestClient(app)

    response = client.post(
        "/reports/weekly",
        headers={
            "X-Worktrace-Owner-Id": "local-owner",
            "X-Worktrace-Report-Token": "dev-only-report-token",
        },
        json={"start_date": "2026-06-08", "end_date": "2026-06-01"},
    )

    assert response.status_code == 422


def test_weekly_report_api_requires_access_headers():
    client = TestClient(app)

    response = client.post("/reports/weekly", json={"start_date": "2026-06-01", "end_date": "2026-06-07"})

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "REPORT_ACCESS_HEADERS_REQUIRED",
        "message": "Report access headers are required.",
    }


def test_weekly_report_api_rejects_other_owner():
    client = TestClient(app)

    response = client.post(
        "/reports/weekly",
        headers={
            "X-Worktrace-Owner-Id": "other-owner",
            "X-Worktrace-Report-Token": "dev-only-report-token",
        },
        json={"start_date": "2026-06-01", "end_date": "2026-06-07"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "REPORT_OWNER_FORBIDDEN",
        "message": "Report owner is not allowed.",
    }


def test_weekly_report_query_uses_owner_filter(monkeypatch):
    from app.services import weekly_report

    captured = []

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            captured.append((query, params))
            if len(captured) == 1:
                return FakeResult([
                    {
                        "id": "00000000-0000-0000-0000-000000000001",
                        "title": "owner project",
                        "description": "",
                        "status": "idea",
                        "role": "",
                        "updated_at": "2026-06-01 00:00:00+00",
                    }
                ])
            return FakeResult([])

    monkeypatch.setattr(weekly_report, "connect", lambda settings: FakeConnection())

    dataset = weekly_report.fetch_weekly_report_dataset(
        Settings(database_url="postgresql://example"),
        date(2026, 6, 1),
        date(2026, 6, 7),
        "local-owner",
    )

    assert dataset.projects[0].title == "owner project"
    assert len(captured) >= 3
    assert all(params["owner_id"] == "local-owner" for _, params in captured)
    assert all("owner_id" in query for query, _ in captured)


def test_report_access_rejects_default_token_outside_local():
    from app.api.security import require_report_access

    settings = Settings(app_env="production", report_access_token="dev-only-report-token")

    try:
        require_report_access("local-owner", "dev-only-report-token", settings)
    except Exception as exc:
        assert getattr(exc, "status_code") == 503
        assert getattr(exc, "detail") == {
            "code": "REPORT_DEFAULT_TOKEN_NOT_ALLOWED",
            "message": "Default report access token cannot be used outside local development.",
        }
    else:
        raise AssertionError("production default token must be rejected")


def test_weekly_report_api_rejects_invalid_token():
    client = TestClient(app)

    response = client.post(
        "/reports/weekly",
        headers={
            "X-Worktrace-Owner-Id": "local-owner",
            "X-Worktrace-Report-Token": "wrong-token",
        },
        json={"start_date": "2026-06-01", "end_date": "2026-06-07"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "REPORT_TOKEN_INVALID",
        "message": "Report access token is invalid.",
    }


def test_weekly_report_api_returns_stable_database_error(monkeypatch):
    def fake_fetch_weekly_report_dataset(settings, start_date, end_date, owner_id):
        raise psycopg.OperationalError("database unavailable")

    monkeypatch.setattr(reports, "fetch_weekly_report_dataset", fake_fetch_weekly_report_dataset)
    client = TestClient(app)

    response = client.post(
        "/reports/weekly",
        headers={
            "X-Worktrace-Owner-Id": "local-owner",
            "X-Worktrace-Report-Token": "dev-only-report-token",
        },
        json={"start_date": "2026-06-01", "end_date": "2026-06-07"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "DATABASE_UNAVAILABLE",
        "message": (
            "Database is unavailable or the report schema is not initialized. "
            "Run `python backend/scripts/init_db.py` or start Docker Compose."
        ),
    }
