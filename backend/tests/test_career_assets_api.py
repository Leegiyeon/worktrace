from uuid import UUID

from fastapi.testclient import TestClient

from app.api import career_assets
from app.main import app
from app.schemas.career_assets import CareerAsset
from app.services import career_assets as career_asset_service
from app.services.career_assets import CareerAssetProjectNotFoundError

HEADERS = {
    "X-Work-Support-Owner-Id": "local-owner",
    "X-Work-Support-Report-Token": "dev-only-report-token",
}
PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def sample_asset() -> CareerAsset:
    return CareerAsset(
        id="00000000-0000-0000-0000-000000000301",
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
