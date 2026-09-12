from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.ai import ProjectAnalystResponse
import app.api.ai as ai_api


client = TestClient(app)


def test_project_analyst_returns_structured_result(monkeypatch):
    project_id = uuid4()
    task_id = uuid4()

    monkeypatch.setattr(
        ai_api,
        "analyze_project",
        lambda settings, owner_id, requested_project_id: ProjectAnalystResponse(
            summary="남은 핵심 WBS를 우선 처리해야 합니다.",
            next_actions=[{"task_id": task_id, "reason": "진행 중인 높은 우선순위 WBS입니다."}],
            blockers=["보류 WBS 1건"],
            needs_attention=[],
            confidence=0.9,
            remaining_wbs_count=3,
            evidence_commit_count=5,
        ),
    )

    response = client.post("/api/ai/project-analyst", json={"project_id": str(project_id)})

    assert response.status_code == 200
    body = response.json()
    assert body["remaining_wbs_count"] == 3
    assert body["next_actions"][0]["task_id"] == str(task_id)


def test_project_analyst_missing_project_returns_404(monkeypatch):
    from app.services.projects import ProjectNotFoundError

    monkeypatch.setattr(ai_api, "analyze_project", lambda *args: (_ for _ in ()).throw(ProjectNotFoundError()))
    response = client.post("/api/ai/project-analyst", json={"project_id": str(uuid4())})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
