from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api import report_snapshots as api
from app.main import app
from app.schemas.report_snapshots import ReportSnapshotDetail, ReportSnapshotPage
from test_auto_report_progress import HEADERS
from test_auto_report_snapshot import activity, build
from test_project_lifecycle_postgres import committed_database


def saved_report():
    report = build(activity())
    return ReportSnapshotDetail(
        id=str(uuid4()), request_id=str(uuid4()), report_type=report.report_type,
        start_date=report.start_date, end_date=report.end_date,
        as_of=report.activity.as_of, created_at=report.activity.as_of,
        fingerprint=report.activity.fingerprint, schema_version="1", report=report,
    )


def test_snapshot_endpoints_forward_authenticated_owner_and_preserve_saved_payload(monkeypatch):
    saved = saved_report()
    calls = []

    def create(settings, owner, request):
        calls.append(("create", owner, str(request.request_id)))
        return saved

    def listing(settings, owner, *, limit, offset):
        calls.append(("list", owner, limit, offset))
        return ReportSnapshotPage(items=[saved], total=3, limit=limit, offset=offset)

    def detail(settings, owner, snapshot_id):
        calls.append(("get", owner, str(snapshot_id)))
        return saved

    def delete(settings, owner, snapshot_id):
        calls.append(("delete", owner, str(snapshot_id)))

    monkeypatch.setattr(api.report_snapshots, "create_report_snapshot", create)
    monkeypatch.setattr(api.report_snapshots, "list_report_snapshots", listing)
    monkeypatch.setattr(api.report_snapshots, "get_report_snapshot", detail)
    monkeypatch.setattr(api.report_snapshots, "delete_report_snapshot", delete)
    client = TestClient(app)
    body = {"request_id": saved.request_id, "report_type": "weekly", "start_date": "2026-09-14", "end_date": "2026-09-18"}
    response = client.post("/reports/snapshots", headers=HEADERS, json=body)
    assert response.status_code == 200
    assert response.json()["report"] == saved.report.model_dump(mode="json")
    response = client.get("/reports/snapshots?limit=2&offset=1", headers=HEADERS)
    assert response.status_code == 200 and response.json()["total"] == 3
    assert "report" not in response.json()["items"][0]
    response = client.get(f"/reports/snapshots/{saved.id}", headers=HEADERS)
    assert response.json()["report"]["markdown"] == saved.report.markdown
    response = client.delete(f"/reports/snapshots/{saved.id}", headers=HEADERS)
    assert response.status_code == 204 and response.content == b""
    assert calls == [("create", "local-owner", saved.request_id), ("list", "local-owner", 2, 1),
                     ("get", "local-owner", saved.id), ("delete", "local-owner", saved.id)]


@pytest.mark.parametrize("method,path", [
    ("get", "/reports/snapshots"), ("post", "/reports/snapshots"),
    ("get", f"/reports/snapshots/{uuid4()}"), ("delete", f"/reports/snapshots/{uuid4()}"),
])
def test_snapshot_routes_require_authentication(method, path):
    assert getattr(TestClient(app), method)(path).status_code == 401


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=x"])
def test_archive_pagination_is_bounded(query):
    assert TestClient(app).get(f"/reports/snapshots?{query}", headers=HEADERS).status_code == 422


def test_create_rejects_client_snapshot_payload_and_invalid_period():
    body = {"request_id": str(uuid4()), "report_type": "daily", "start_date": "2026-09-18", "end_date": "2026-09-18"}
    client = TestClient(app)
    assert client.post("/reports/snapshots", headers=HEADERS, json={**body, "report": {"markdown": "forged"}}).status_code == 422
    assert client.post("/reports/snapshots", headers=HEADERS, json={**body, "end_date": "2026-09-19"}).status_code == 422
    assert client.post("/reports/snapshots", headers=HEADERS, json={**body, "request_id": "bad"}).status_code == 422


@pytest.mark.parametrize("exception,expected,code", [
    (api.report_snapshots.ReportSnapshotNotFoundError, 404, "REPORT_SNAPSHOT_NOT_FOUND"),
    (api.report_snapshots.ReportSnapshotIntegrityError, 500, "REPORT_SNAPSHOT_INTEGRITY_ERROR"),
    (psycopg.OperationalError, 503, "DATABASE_UNAVAILABLE"),
])
def test_snapshot_read_errors_are_safe_and_explicit(monkeypatch, exception, expected, code):
    def fail(*args):
        raise exception("private raw source must never be returned")
    monkeypatch.setattr(api.report_snapshots, "get_report_snapshot", fail)
    response = TestClient(app).get(f"/reports/snapshots/{uuid4()}", headers=HEADERS)
    assert response.status_code == expected and response.json()["detail"]["code"] == code
    assert "private raw source" not in response.text


def test_reused_request_with_changed_parameters_is_a_conflict(monkeypatch):
    def fail(*args):
        raise api.report_snapshots.ReportSnapshotConflictError()
    monkeypatch.setattr(api.report_snapshots, "create_report_snapshot", fail)
    response = TestClient(app).post("/reports/snapshots", headers=HEADERS, json={
        "request_id": str(uuid4()), "report_type": "daily", "start_date": "2026-09-18", "end_date": "2026-09-18",
    })
    assert response.status_code == 409


def test_archive_api_round_trip_uses_real_storage_and_survives_source_deletion(committed_database, monkeypatch):
    from app.services import auto_report, projects

    connection = committed_database
    monkeypatch.setattr(api.report_snapshots, "connect", projects.connect)
    monkeypatch.setattr(auto_report, "connect", projects.connect)
    project_id = connection.execute("INSERT INTO projects(owner_id,title) VALUES('local-owner','Original source') RETURNING id").fetchone()["id"]
    connection.execute("INSERT INTO work_logs(owner_id,project_id,log_date,title,content) VALUES('local-owner',%s,'2026-09-18','Recorded work','Private saved evidence')", (project_id,))
    connection.commit()
    client = TestClient(app)
    body = {"request_id": str(uuid4()), "report_type": "daily", "start_date": "2026-09-18", "end_date": "2026-09-18"}
    created = client.post("/reports/snapshots", headers=HEADERS, json=body)
    assert created.status_code == 200
    saved = created.json()
    assert "Private saved evidence" in saved["report"]["markdown"]
    connection.execute("DELETE FROM projects WHERE id=%s", (project_id,))
    connection.execute("DELETE FROM work_logs WHERE owner_id='local-owner'")
    connection.commit()
    retrieved = client.get(f"/reports/snapshots/{saved['id']}", headers=HEADERS)
    assert retrieved.status_code == 200 and retrieved.json() == saved
    assert client.post("/reports/snapshots", headers=HEADERS, json=body).json() == saved
    listing = client.get("/reports/snapshots", headers=HEADERS).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == saved["id"]
    assert "report" not in listing["items"][0]
    assert client.delete(f"/reports/snapshots/{saved['id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/reports/snapshots/{saved['id']}", headers=HEADERS).status_code == 404
