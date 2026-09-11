from datetime import date
from uuid import UUID

from fastapi.testclient import TestClient

from app.api import work_logs
from app.main import app
from app.schemas.reports import WorkLogItem
from app.services.work_logs import WorkLogNotFoundError, WorkLogProjectNotFoundError

HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"
WORK_LOG_ID = "00000000-0000-0000-0000-000000000201"


def sample_work_log(**overrides) -> WorkLogItem:
    data = {
        "id": WORK_LOG_ID,
        "log_date": date(2026, 6, 1),
        "work_type": "planning",
        "title": "요구사항 정리",
        "content": "프로젝트별 업무 로그 입력 항목을 정리했다.",
        "decisions": "경력 근거로 쓰기 위해 판단/결정 필드를 분리한다.",
        "collaborators": "PM, 개발자",
        "next_actions": "상세 화면에 타임라인을 연결한다.",
        "duration_minutes": 90,
        "blockers": "",
        "project_id": PROJECT_ID,
        "project_title": "업무 플랫폼 MVP",
        "updated_at": "2026-06-01 12:00:00+00",
    }
    data.update(overrides)
    return WorkLogItem(**data)


def test_work_log_crud_routes_use_owner_context(monkeypatch):
    calls = []

    def fake_list_work_logs(settings, owner_id, start_date, end_date, project_id):
        calls.append(("list", owner_id, start_date, end_date, project_id))
        return [sample_work_log()]

    def fake_create_work_log(settings, owner_id, payload):
        calls.append(("create", owner_id, payload.project_id, payload.work_type, payload.duration_minutes))
        return sample_work_log(title=payload.title, work_type=payload.work_type, duration_minutes=payload.duration_minutes)

    def fake_get_work_log(settings, owner_id, work_log_id):
        calls.append(("get", owner_id, work_log_id))
        return sample_work_log()

    def fake_update_work_log(settings, owner_id, work_log_id, payload):
        calls.append(("patch", owner_id, work_log_id, payload.next_actions))
        return sample_work_log(next_actions=payload.next_actions or "")

    def fake_delete_work_log(settings, owner_id, work_log_id):
        calls.append(("delete", owner_id, work_log_id))

    monkeypatch.setattr(work_logs, "list_work_logs", fake_list_work_logs)
    monkeypatch.setattr(work_logs, "create_work_log", fake_create_work_log)
    monkeypatch.setattr(work_logs, "get_work_log", fake_get_work_log)
    monkeypatch.setattr(work_logs, "update_work_log", fake_update_work_log)
    monkeypatch.setattr(work_logs, "delete_work_log", fake_delete_work_log)
    client = TestClient(app)

    list_response = client.get(
        f"/work-logs?project_id={PROJECT_ID}&start_date=2026-06-01&end_date=2026-06-07",
        headers=HEADERS,
    )
    create_response = client.post(
        "/work-logs",
        headers=HEADERS,
        json={
            "project_id": PROJECT_ID,
            "log_date": "2026-06-01",
            "work_type": "planning",
            "title": "요구사항 정리",
            "content": "수행 내용",
            "decisions": "내 판단",
            "collaborators": "PM",
            "next_actions": "다음 액션",
            "duration_minutes": 90,
        },
    )
    detail_response = client.get(f"/work-logs/{WORK_LOG_ID}", headers=HEADERS)
    patch_response = client.patch(
        f"/work-logs/{WORK_LOG_ID}",
        headers=HEADERS,
        json={"next_actions": "내일 상세 UI 검증"},
    )
    delete_response = client.delete(f"/work-logs/{WORK_LOG_ID}", headers=HEADERS)

    assert list_response.status_code == 200
    assert list_response.json()[0]["work_type"] == "planning"
    assert list_response.json()[0]["duration_minutes"] == 90
    assert create_response.status_code == 201
    assert create_response.json()["title"] == "요구사항 정리"
    assert create_response.json()["decisions"] == "경력 근거로 쓰기 위해 판단/결정 필드를 분리한다."
    assert detail_response.status_code == 200
    assert patch_response.status_code == 200
    assert patch_response.json()["next_actions"] == "내일 상세 UI 검증"
    assert delete_response.status_code == 204
    assert calls[0] == ("list", "local-owner", date(2026, 6, 1), date(2026, 6, 7), UUID(PROJECT_ID))
    assert calls[1] == ("create", "local-owner", UUID(PROJECT_ID), "planning", 90)
    assert calls[4] == ("delete", "local-owner", UUID(WORK_LOG_ID))


def test_work_log_api_reports_not_found(monkeypatch):
    def fake_get_work_log(settings, owner_id, work_log_id):
        raise WorkLogNotFoundError()

    monkeypatch.setattr(work_logs, "get_work_log", fake_get_work_log)
    client = TestClient(app)

    response = client.get(f"/work-logs/{WORK_LOG_ID}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "WORK_LOG_NOT_FOUND",
        "message": "Work log was not found.",
    }


def test_work_log_api_reports_missing_project(monkeypatch):
    def fake_create_work_log(settings, owner_id, payload):
        raise WorkLogProjectNotFoundError()

    monkeypatch.setattr(work_logs, "create_work_log", fake_create_work_log)
    client = TestClient(app)

    response = client.post(
        "/work-logs",
        headers=HEADERS,
        json={"project_id": PROJECT_ID, "log_date": "2026-06-01", "title": "연결 실패"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "PROJECT_NOT_FOUND",
        "message": "Project was not found.",
    }


def test_work_log_period_requires_pair() -> None:
    client = TestClient(app)

    response = client.get("/work-logs?start_date=2026-06-01", headers=HEADERS)

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "INVALID_PERIOD",
        "message": "start_date and end_date must be provided together.",
    }
