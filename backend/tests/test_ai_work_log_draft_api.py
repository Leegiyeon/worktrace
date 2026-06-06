from uuid import UUID

from fastapi.testclient import TestClient

from app.api import ai
from app.core.config import Settings
from app.main import app
from app.schemas.ai import WorkLogDraftRequest, WorkLogDraftResponse
from app.services import ai_work_log_draft
from app.services.ai_work_log_draft import AiConfigurationError, AiDraftProjectNotFoundError

HEADERS = {
    "X-Work-Support-Owner-Id": "local-owner",
    "X-Work-Support-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def sample_draft(**overrides) -> WorkLogDraftResponse:
    data = {
        "title": "주간 회의 정리",
        "work_type": "meeting",
        "content": "주간 회의 내용을 정리했다.",
        "decisions": "",
        "collaborators": "",
        "next_actions": "후속 액션 확인",
        "blockers": "",
        "duration_minutes": 0,
        "confidence": 0.82,
    }
    data.update(overrides)
    return WorkLogDraftResponse(**data)


def test_ai_work_log_draft_route_uses_owner_context(monkeypatch):
    calls = []

    def fake_generate_work_log_draft(settings, owner_id, payload):
        calls.append((owner_id, payload))
        return sample_draft()

    monkeypatch.setattr(ai, "generate_work_log_draft", fake_generate_work_log_draft)
    client = TestClient(app)

    response = client.post(
        "/ai/work-log-draft",
        headers=HEADERS,
        json={"raw_text": "오늘 주간 회의 정리", "project_id": PROJECT_ID},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "주간 회의 정리"
    assert calls[0][0] == "local-owner"
    assert calls[0][1].project_id == UUID(PROJECT_ID)


def test_ai_work_log_draft_missing_config_returns_safe_error(monkeypatch):
    def fake_generate_work_log_draft(settings, owner_id, payload):
        raise AiConfigurationError()

    monkeypatch.setattr(ai, "generate_work_log_draft", fake_generate_work_log_draft)
    client = TestClient(app)

    response = client.post("/ai/work-log-draft", headers=HEADERS, json={"raw_text": "업무 메모"})

    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "AI_CONFIG_MISSING", "message": "AI 설정이 필요합니다."}


def test_ai_work_log_draft_project_not_found(monkeypatch):
    def fake_generate_work_log_draft(settings, owner_id, payload):
        raise AiDraftProjectNotFoundError()

    monkeypatch.setattr(ai, "generate_work_log_draft", fake_generate_work_log_draft)
    client = TestClient(app)

    response = client.post(
        "/ai/work-log-draft",
        headers=HEADERS,
        json={"raw_text": "업무 메모", "project_id": PROJECT_ID},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_service_uses_openai_responses_parse_without_real_api(monkeypatch):
    calls = []

    class FakeResponses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            return type("FakeResponse", (), {"output_parsed": sample_draft(duration_minutes=45)})()

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setattr(ai_work_log_draft, "OpenAI", FakeOpenAI)
    settings = Settings(openai_api_key="test-key", openai_model="test-model")

    draft = ai_work_log_draft.generate_work_log_draft(
        settings,
        "local-owner",
        WorkLogDraftRequest(raw_text="45분 동안 회의록 정리"),
    )

    assert draft.duration_minutes == 45
    assert calls[0]["model"] == "test-model"
    assert calls[0]["text_format"] is WorkLogDraftResponse


def test_service_zeroes_duration_when_not_explicitly_mentioned(monkeypatch):
    class FakeResponses:
        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": sample_draft(duration_minutes=90)})()

    class FakeOpenAI:
        def __init__(self, api_key):
            self.responses = FakeResponses()

    monkeypatch.setattr(ai_work_log_draft, "OpenAI", FakeOpenAI)
    settings = Settings(openai_api_key="test-key", openai_model="test-model")

    draft = ai_work_log_draft.generate_work_log_draft(
        settings,
        "local-owner",
        WorkLogDraftRequest(raw_text="회의록 정리하고 다음 액션 확인"),
    )

    assert draft.duration_minutes == 0
