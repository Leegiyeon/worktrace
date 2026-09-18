from datetime import date, datetime, timezone
from contextlib import contextmanager

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api import reports
from app.main import app
from app.schemas.projects import ProjectSummary
from app.services.auto_report import build_auto_report_response
from app.services import auto_report
from app.schemas.report_activity import ReportActivity
from test_weekly_report import sample_dataset

AS_OF = "2026-09-18T00:00:00Z"
HEADERS = {"X-Worktrace-Owner-Id": "local-owner", "X-Worktrace-Report-Token": "dev-only-report-token"}


def summary(**overrides):
    return ProjectSummary(**{
        "id": sample_dataset().projects[0].id, "title": "Project", "status": "done",
        "updated_at": AS_OF, "total_tasks": 4, "completed_tasks": 1, "remaining_tasks": 3,
        "progress_basis": "wbs", "progress_percent": 25, "derived_task_count": 0,
        "progress_plan_status": "approved", "progress_plan_version": 1, **overrides,
    })


@pytest.mark.parametrize("basis,percent,derived,label,expected", [
    ("unscoped", 0, 0, "산정 전", None),
    ("wbs", 0, 0, "0%", 0),
    ("wbs", 25, 0, "25%", 25),
    ("milestone", 63, 0, "63%", 63),
    ("milestone", 100, 4, "100%", 100),
])
def test_report_reuses_current_project_progress_without_inventing_scores(basis, percent, derived, label, expected):
    current = summary(progress_basis=basis, progress_percent=percent, derived_task_count=derived)
    report = build_auto_report_response(sample_dataset(), "weekly", date(2026, 6, 1), date(2026, 6, 7), [current], AS_OF)
    candidate = report.progress_candidates[0]
    assert candidate.progress_percent == candidate.suggested_progress_percent == expected
    assert candidate.total_tasks == 4 and candidate.completed_tasks == 1
    assert candidate.progress_basis == basis and candidate.derived_task_count == derived
    assert candidate.progress_plan_status == "approved" and candidate.progress_plan_version == 1
    assert candidate.provenance == label and candidate.as_of == AS_OF
    assert "## 현재 WBS 진척" in report.markdown and AS_OF in report.markdown and label in report.markdown
    assert "진행률 후보" not in report.markdown


def test_missing_current_summary_stays_unknown_even_for_active_project_with_documents():
    report = build_auto_report_response(sample_dataset(), "daily", date(2026, 6, 1), date(2026, 6, 1), [], AS_OF)
    candidate = report.progress_candidates[0]
    assert candidate.progress_basis == "unknown" and candidate.progress_percent is None
    assert candidate.total_tasks is None and candidate.provenance == "기준 미확인"


@pytest.mark.parametrize("state,label", [("unapproved", "계획 미승인"), ("stale", "계획 재승인 필요")])
def test_report_never_presents_unapproved_or_stale_progress_as_percent(state, label):
    report = build_auto_report_response(sample_dataset(), "weekly", date(2026, 6, 1), date(2026, 6, 7),
                                        [summary(progress_plan_status=state, progress_percent=100)], AS_OF)
    candidate = report.progress_candidates[0]
    assert candidate.progress_percent is None and candidate.suggested_progress_percent is None
    assert candidate.provenance == label
    assert "100%" not in report.markdown


def fake_snapshot(monkeypatch):
    class Connection:
        def execute(self, statement):
            return self

        def fetchone(self):
            return {"as_of": datetime(2026, 9, 18, tzinfo=timezone.utc)}

    connection = Connection()

    @contextmanager
    def connect(settings):
        yield connection

    monkeypatch.setattr(auto_report, "connect", connect)
    monkeypatch.setattr(auto_report, "fetch_weekly_report_dataset", lambda *args, **kwargs: sample_dataset())
    monkeypatch.setattr(auto_report, "fetch_report_activity", lambda *args: ReportActivity(
        as_of=AS_OF, timezone="Asia/Seoul", start_at=AS_OF, end_exclusive=AS_OF,
        transitions=[], current_tasks=[], issues=[], outcomes=[],
    ))
    return connection


def test_report_api_fetches_owner_scoped_canonical_summary(monkeypatch):
    shared_connection = fake_snapshot(monkeypatch)

    def current(settings, owner, *, connection):
        assert owner == "local-owner"
        assert connection is shared_connection
        return [summary()]

    monkeypatch.setattr(auto_report, "list_projects", current)
    response = TestClient(app).post("/reports/automatic", headers=HEADERS,
        json={"report_type": "weekly", "start_date": "2026-06-01", "end_date": "2026-06-07"})
    assert response.status_code == 200
    assert response.json()["progress_candidates"][0]["progress_percent"] == 25


def test_report_does_not_fallback_to_estimates_when_summary_query_fails(monkeypatch):
    fake_snapshot(monkeypatch)

    def unavailable(*args, **kwargs):
        raise psycopg.OperationalError("unavailable")

    monkeypatch.setattr(auto_report, "list_projects", unavailable)
    response = TestClient(app).post("/reports/automatic", headers=HEADERS,
        json={"report_type": "weekly", "start_date": "2026-06-01", "end_date": "2026-06-07"})
    assert response.status_code == 503
