from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import career_assets
from app.core.config import Settings
from app.main import app
from app.schemas.career_assets import CareerAsset, CareerAssetAiContent, CareerAssetUpdateRequest
from app.services import career_assets as career_asset_service
from app.services.career_assets import CareerAssetNotFoundError, CareerAssetProjectNotFoundError

HEADERS = {
    "X-Worktrace-Owner-Id": "local-owner",
    "X-Worktrace-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"
CAREER_ASSET_ID = "00000000-0000-0000-0000-000000000301"


def sample_asset() -> CareerAsset:
    return CareerAsset(
        id=CAREER_ASSET_ID,
        project_id=PROJECT_ID,
        source_summary="업무 로그 2건",
        work_summary="업무 요약",
        outcome_summary="성과 요약",
        resume_bullets="- 이력서 문장",
        career_description="경력기술서",
        portfolio_description="포트폴리오",
        star_answer="STAR",
        markdown="## Career",
        generation_method="seed_template",
        created_at="2026-06-01 12:00:00+00",
        updated_at="2026-06-01 12:00:00+00",
    )


def test_career_asset_list_route_uses_owner_context(monkeypatch):
    calls = []

    def fake_list_project_career_assets(settings, owner_id, project_id):
        calls.append((owner_id, project_id))
        return [sample_asset()]

    monkeypatch.setattr(career_assets, "list_project_career_assets", fake_list_project_career_assets)
    client = TestClient(app)

    response = client.get(f"/projects/{PROJECT_ID}/career-assets", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()[0]["generation_method"] == "seed_template"
    assert calls == [("local-owner", UUID(PROJECT_ID))]


def test_career_asset_list_returns_project_not_found(monkeypatch):
    def fake_list_project_career_assets(settings, owner_id, project_id):
        raise CareerAssetProjectNotFoundError()

    monkeypatch.setattr(career_assets, "list_project_career_assets", fake_list_project_career_assets)
    client = TestClient(app)

    response = client.get(f"/projects/{PROJECT_ID}/career-assets", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_career_asset_generate_route_uses_owner_context(monkeypatch):
    calls = []

    def fake_generate_project_career_asset(settings, owner_id, project_id, target_role):
        calls.append((owner_id, project_id, target_role))
        return sample_asset()

    monkeypatch.setattr(career_assets, "generate_project_career_asset", fake_generate_project_career_asset)
    client = TestClient(app)

    response = client.post(
        f"/projects/{PROJECT_ID}/career-assets/generate",
        headers=HEADERS,
        json={"target_role": "AI서비스기획"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == sample_asset().id
    assert calls == [("local-owner", UUID(PROJECT_ID), "AI서비스기획")]


def test_career_asset_generate_returns_project_not_found(monkeypatch):
    def fake_generate_project_career_asset(settings, owner_id, project_id, target_role):
        raise CareerAssetProjectNotFoundError()

    monkeypatch.setattr(career_assets, "generate_project_career_asset", fake_generate_project_career_asset)
    client = TestClient(app)

    response = client.post(
        f"/projects/{PROJECT_ID}/career-assets/generate",
        headers=HEADERS,
        json={"target_role": "PM"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_career_asset_patch_route_uses_owner_context_and_preserves_generation_method(monkeypatch):
    calls = []

    def fake_update_project_career_asset(settings, owner_id, project_id, career_asset_id, payload):
        calls.append((owner_id, project_id, career_asset_id, payload))
        asset = sample_asset()
        return asset.model_copy(
            update={
                "work_summary": payload.work_summary,
                "resume_bullets": payload.resume_bullets,
                "generation_method": asset.generation_method,
            }
        )

    monkeypatch.setattr(career_assets, "update_project_career_asset", fake_update_project_career_asset)
    client = TestClient(app)

    response = client.patch(
        f"/projects/{PROJECT_ID}/career-assets/{CAREER_ASSET_ID}",
        headers=HEADERS,
        json={
            "source_summary": "클라이언트가 바꾸려는 근거",
            "work_summary": "사용자가 고친 업무 요약",
            "resume_bullets": "- 사용자가 고친 이력서 문장",
            "generation_method": "manual",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["work_summary"] == "사용자가 고친 업무 요약"
    assert body["resume_bullets"] == "- 사용자가 고친 이력서 문장"
    assert body["generation_method"] == "seed_template"
    assert calls[0][:3] == ("local-owner", UUID(PROJECT_ID), UUID(CAREER_ASSET_ID))
    assert not hasattr(calls[0][3], "source_summary")
    assert not hasattr(calls[0][3], "generation_method")


def test_career_asset_update_service_scopes_query_and_preserves_evidence(monkeypatch):
    captured = []
    stored_asset = sample_asset().model_dump()

    class FakeResult:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            captured.append((query, params))
            if "SELECT id FROM projects" in query:
                return FakeResult({"id": PROJECT_ID})
            updated = {
                **stored_asset,
                "work_summary": params["work_summary"] or stored_asset["work_summary"],
            }
            return FakeResult(updated)

    monkeypatch.setattr(career_asset_service, "connect", lambda settings: FakeConnection())

    updated = career_asset_service.update_project_career_asset(
        Settings(database_url="postgresql://example"),
        "local-owner",
        UUID(PROJECT_ID),
        UUID(CAREER_ASSET_ID),
        CareerAssetUpdateRequest(work_summary="사용자 수정"),
    )

    update_query, update_params = captured[1]
    update_set_clause = update_query.split("WHERE", 1)[0]
    assert updated.work_summary == "사용자 수정"
    assert updated.source_summary == stored_asset["source_summary"]
    assert "source_summary =" not in update_set_clause
    assert "generation_method =" not in update_set_clause
    assert "source_summary" not in update_params
    assert update_params["owner_id"] == "local-owner"
    assert update_params["project_id"] == UUID(PROJECT_ID)
    assert update_params["career_asset_id"] == UUID(CAREER_ASSET_ID)
    assert "owner_id = %(owner_id)s" in update_query
    assert "project_id = %(project_id)s" in update_query
    assert "id = %(career_asset_id)s" in update_query


def test_career_asset_update_service_blocks_unknown_owner(monkeypatch):
    captured = []

    class FakeResult:
        def fetchone(self):
            return None

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            captured.append((query, params))
            return FakeResult()

    monkeypatch.setattr(career_asset_service, "connect", lambda settings: FakeConnection())

    with pytest.raises(CareerAssetProjectNotFoundError):
        career_asset_service.update_project_career_asset(
            Settings(database_url="postgresql://example"),
            "other-owner",
            UUID(PROJECT_ID),
            UUID(CAREER_ASSET_ID),
            CareerAssetUpdateRequest(work_summary="권한 없는 수정"),
        )

    assert len(captured) == 1
    assert captured[0][1]["owner_id"] == "other-owner"


def test_career_asset_patch_returns_project_not_found(monkeypatch):
    def fake_update_project_career_asset(settings, owner_id, project_id, career_asset_id, payload):
        raise CareerAssetProjectNotFoundError()

    monkeypatch.setattr(career_assets, "update_project_career_asset", fake_update_project_career_asset)
    client = TestClient(app)

    response = client.patch(
        f"/projects/{PROJECT_ID}/career-assets/{CAREER_ASSET_ID}",
        headers=HEADERS,
        json={"work_summary": "사용자 수정"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_career_asset_patch_returns_career_asset_not_found(monkeypatch):
    def fake_update_project_career_asset(settings, owner_id, project_id, career_asset_id, payload):
        raise CareerAssetNotFoundError()

    monkeypatch.setattr(career_assets, "update_project_career_asset", fake_update_project_career_asset)
    client = TestClient(app)

    response = client.patch(
        f"/projects/{PROJECT_ID}/career-assets/{CAREER_ASSET_ID}",
        headers=HEADERS,
        json={"work_summary": "사용자 수정"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CAREER_ASSET_NOT_FOUND"


def test_template_generation_does_not_fabricate_metric_values():
    content = career_asset_service._build_career_asset_content(
        {"title": "업무지원", "status": "in_progress", "role": "PM"},
        [{"title": "성과 후보 확인", "status": "done"}],
        [{"title": "성과 후보 정리"}],
        [
            {
                "title": "성과 후보를 확정 성과로 전환",
                "after_state": "사용자가 확인한 성과만 저장",
                "metric_name": "전환율",
                "metric_value": None,
                "metric_unit": "%",
                "evidence_work_log_ids": ["00000000-0000-0000-0000-000000000501"],
                "resume_ready": True,
            }
        ],
        "PM",
    )

    assert "전환율" not in content["resume_bullets"]
    assert "%" not in content["resume_bullets"]
    assert "사용자가 확인한 성과만 저장" in content["markdown"]
    assert content["generation_method"] == "template:PM"


def test_ai_generation_receives_all_evidence_without_real_api(monkeypatch):
    calls = []

    class FakeResponses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            return type("Response", (), {"output_parsed": CareerAssetAiContent(
                work_summary="커밋과 업무 로그를 함께 검토했다.",
                outcome_summary="확정 성과만 반영했다.",
                resume_bullets="- main 커밋 근거와 WBS 이력을 연결해 업무 추적 체계를 구축",
                career_description="경력기술서",
                portfolio_description="포트폴리오",
                star_answer="Situation: 근거 분산\nTask: 통합\nAction: 연결\nResult: 확인 필요",
            )})()

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setattr(career_asset_service, "OpenAI", FakeOpenAI)
    fallback = career_asset_service._build_career_asset_content(
        {"title": "worktrace", "status": "in_progress", "role": "PM"}, [], [], [], "PM", []
    )
    result = career_asset_service._build_ai_career_asset_content(
        Settings(openai_api_key="test-key", openai_model="test-model"),
        {"title": "worktrace", "status": "in_progress", "role": "PM"},
        [{"title": "Webhook", "status": "done"}],
        [{"title": "설계 기록"}],
        [{"title": "자동 수집", "resume_ready": True}],
        [{"sha": "abc", "message": "Add webhook"}],
        "PM",
        fallback,
    )

    assert result["generation_method"] == "openai:PM"
    assert "커밋 근거" in result["resume_bullets"]
    assert calls[0]["model"] == "test-model"
    assert calls[0]["text_format"] is CareerAssetAiContent
    assert "Add webhook" in calls[0]["input"][1]["content"]
