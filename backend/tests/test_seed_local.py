from datetime import date

import pytest

from app.core.config import Settings
from scripts.seed_local import SAMPLE_PREFIX, USER_PROJECT_GENERATION_METHOD, USER_PROJECT_PREFIX, _user_project_seed_data, ensure_local_environment


def test_seed_local_guard_allows_local_environment() -> None:
    ensure_local_environment(Settings(app_env="local"))
    ensure_local_environment(Settings(app_env="dev"))
    ensure_local_environment(Settings(app_env="test"))


def test_seed_local_guard_rejects_non_local_without_force() -> None:
    with pytest.raises(RuntimeError, match="local/dev/test only"):
        ensure_local_environment(Settings(app_env="production"))


def test_seed_local_guard_can_be_forced() -> None:
    ensure_local_environment(Settings(app_env="production"), force=True)


def test_seed_local_sample_marker_is_explicit() -> None:
    assert SAMPLE_PREFIX == "[샘플]"


def test_user_project_seed_shape_is_local_and_evidence_safe() -> None:
    seeds = _user_project_seed_data(date(2026, 6, 1))

    assert [seed["title"] for seed in seeds] == [
        f"{USER_PROJECT_PREFIX} worktrace",
        f"{USER_PROJECT_PREFIX} OCC AI 민원 플랫폼",
        f"{USER_PROJECT_PREFIX} E-manual RAG Chatbot",
    ]
    for seed in seeds:
        assert "local/dev seed" in seed["description"]
        assert 3 <= len(seed["tasks"]) <= 5
        assert 2 <= len(seed["work_logs"]) <= 3
        assert 1 <= len(seed["outcomes"]) <= 2
        assert seed["career_asset"]["source_summary"].startswith(USER_PROJECT_GENERATION_METHOD)
        for outcome in seed["outcomes"]:
            assert outcome["outcome_type"] == "qualitative"
            assert outcome["metric_value"] is None
            assert outcome["metric_unit"] == "추정 입력 필요"
            assert outcome["resume_ready"] is False
