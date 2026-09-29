from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api import work_requests
from app.main import app
from app.schemas.work_requests import WorkRequest, WorkRequestPage
from app.services.projects import ProjectNotFoundError
from app.services.work_requests import WorkRequestConflictError


HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def test_request_api_requires_owner_and_preserves_request_id(monkeypatch):
    seen = []
    request_id = str(uuid4())

    def fake_create(settings, owner_id, project_id, payload):
        seen.append((owner_id, project_id, payload))
        return WorkRequest(
            id=str(uuid4()), project_id=str(project_id), created_at="2026-09-29T00:00:00Z",
            **payload.model_dump(),
        )

    monkeypatch.setattr(work_requests, "create_work_request", fake_create)
    client = TestClient(app)
    payload = {"request_id": request_id, "title": " 결과 공유 개선 ", "body": "모바일 이탈 감소"}
    assert client.post(f"/projects/{PROJECT_ID}/requests", json=payload).status_code == 401
    response = client.post(f"/projects/{PROJECT_ID}/requests", json=payload, headers=HEADERS)
    assert response.status_code == 201
    assert response.json()["title"] == "결과 공유 개선"
    assert response.json()["request_id"] == request_id
    assert seen[0][0:2] == ("local-owner", UUID(PROJECT_ID))


def test_request_api_rejects_bad_payload_and_reports_conflict(monkeypatch):
    client = TestClient(app)
    url = f"/projects/{PROJECT_ID}/requests"
    assert client.post(url, json={"request_id": str(uuid4()), "title": "  "}, headers=HEADERS).status_code == 422
    assert client.post(url, json={"request_id": str(uuid4()), "title": "Valid", "status": "done"}, headers=HEADERS).status_code == 422

    def conflict(*args):
        raise WorkRequestConflictError()

    monkeypatch.setattr(work_requests, "create_work_request", conflict)
    response = client.post(url, json={"request_id": str(uuid4()), "title": "Valid"}, headers=HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "WORK_REQUEST_CONFLICT"


def test_request_list_scopes_project_and_owner(monkeypatch):
    seen = []

    def fake_list(settings, owner_id, project_id, limit, offset):
        seen.append((owner_id, project_id, limit, offset))
        return WorkRequestPage(items=[], total=0, limit=limit, offset=offset)

    monkeypatch.setattr(work_requests, "list_work_requests", fake_list)
    client = TestClient(app)
    response = client.get(f"/projects/{PROJECT_ID}/requests?limit=5&offset=10", headers=HEADERS)
    assert response.status_code == 200
    assert seen == [("local-owner", UUID(PROJECT_ID), 5, 10)]

    monkeypatch.setattr(work_requests, "list_work_requests", lambda *args: (_ for _ in ()).throw(ProjectNotFoundError()))
    assert client.get(f"/projects/{PROJECT_ID}/requests", headers=HEADERS).status_code == 404
