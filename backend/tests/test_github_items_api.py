from uuid import UUID

from fastapi.testclient import TestClient

from app.api import github_items
from app.main import app
from app.schemas.github_items import GitHubItem, GitHubItemCounts, GitHubItemListResponse
from app.services.github_items import GitHubItemConflictError, GitHubItemNotFoundError, _isoformat, _safe_github_url


HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"
ITEM_ID = "00000000-0000-0000-0000-000000000201"
REQUEST_ID = "00000000-0000-0000-0000-000000000301"


def sample_item(**overrides) -> GitHubItem:
    data = {
        "id": ITEM_ID,
        "number": 42,
        "kind": "issue",
        "title": "Review imported issue",
        "body": "body",
        "body_truncated": False,
        "url": "https://github.com/Owner/repo/issues/42",
        "external_state": "open",
        "source_updated_at": "2026-09-18 01:00:00+00",
        "collected_at": "2026-09-18 01:01:00+00",
        "review_status": "pending",
        "version": 0,
        "task_id": None,
        "task_title": None,
        "reviewed_at": None,
        "source_changed": False,
    }
    data.update(overrides)
    return GitHubItem(**data)


def test_github_item_list_contract_uses_owner_project_scope(monkeypatch):
    calls = []

    def fake_list(settings, owner_id, project_id, review_status, limit, offset):
        calls.append((owner_id, project_id, review_status, limit, offset))
        return GitHubItemListResponse(
            items=[sample_item()],
            total=1,
            counts=GitHubItemCounts(pending=1, adopted=2, ignored=3),
        )

    monkeypatch.setattr(github_items, "list_github_items", fake_list)
    response = TestClient(app).get(
        f"/projects/{PROJECT_ID}/github-items?review_status=all&limit=20&offset=5",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["counts"] == {"pending": 1, "adopted": 2, "ignored": 3}
    assert response.json()["items"][0]["body_truncated"] is False
    assert calls == [("local-owner", UUID(PROJECT_ID), "all", 20, 5)]


def test_github_item_decision_contract_passes_expected_version_source_and_request(monkeypatch):
    calls = []

    def fake_decide(settings, owner_id, project_id, item_id, payload):
        calls.append((owner_id, project_id, item_id, payload.action, payload.expected_version, payload.request_id, payload.title))
        return sample_item(review_status="adopted", version=1, task_id="00000000-0000-0000-0000-000000000401")

    monkeypatch.setattr(github_items, "decide_github_item", fake_decide)
    response = TestClient(app).post(
        f"/projects/{PROJECT_ID}/github-items/{ITEM_ID}/decision",
        headers=HEADERS,
        json={
            "action": "create",
            "expected_version": 0,
            "expected_source_updated_at": "2026-09-18T01:00:00Z",
            "request_id": REQUEST_ID,
            "title": " Adopt issue ",
            "counts_toward_progress": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "adopted"
    assert calls[0][:5] == ("local-owner", UUID(PROJECT_ID), UUID(ITEM_ID), "create", 0)
    assert str(calls[0][5]) == REQUEST_ID
    assert calls[0][6] == "Adopt issue"


def test_github_item_decision_stable_errors(monkeypatch):
    def conflict(*args, **kwargs):
        raise GitHubItemConflictError()

    def missing(*args, **kwargs):
        raise GitHubItemNotFoundError()

    client = TestClient(app)
    payload = {
        "action": "ignore",
        "expected_version": 0,
        "expected_source_updated_at": "2026-09-18T01:00:00Z",
        "request_id": REQUEST_ID,
    }

    monkeypatch.setattr(github_items, "decide_github_item", conflict)
    conflict_response = client.post(f"/projects/{PROJECT_ID}/github-items/{ITEM_ID}/decision", headers=HEADERS, json=payload)
    monkeypatch.setattr(github_items, "decide_github_item", missing)
    missing_response = client.post(f"/projects/{PROJECT_ID}/github-items/{ITEM_ID}/decision", headers=HEADERS, json=payload)

    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"]["code"] == "GITHUB_ITEM_DECISION_CONFLICT"
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"]["code"] == "GITHUB_ITEM_NOT_FOUND"


def test_malformed_github_url_is_sanitized():
    assert _safe_github_url("https://[bad") == ""
    assert _safe_github_url("https://github.com/Owner/repo/issues/1") == "https://github.com/Owner/repo/issues/1"


def test_datetime_output_is_browser_safe_iso():
    assert _isoformat("2026-09-18 01:00:00+00") == "2026-09-18T01:00:00+00:00"
