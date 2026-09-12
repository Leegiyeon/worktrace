from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_analyst_filters_ai_task_ids_against_real_pending_wbs():
    source = (ROOT / "app/services/ai_project_analyst.py").read_text()
    assert "allowed_task_ids" in source
    assert "if str(item.task_id) in allowed_task_ids" in source
    assert 'item["status"] != "done"' in source


def test_project_analyst_uses_planned_wbs_and_commits_as_context_only():
    source = (ROOT / "app/services/ai_project_analyst.py").read_text()
    assert "counts_toward_progress=true" in source
    assert "FROM github_commits" in source
    assert "GitHub commit 개수나 활동량만으로 진척 또는 완료를 판단하지 않는다" in source


def test_project_analyst_surfaces_missing_governance():
    source = (ROOT / "app/services/ai_project_analyst.py").read_text()
    assert "프로젝트 목표와 성취 기준을 먼저 명확히 정의해야 합니다." in source
    assert "프로젝트 마일스톤과 가중치를 정의해야 합니다." in source
