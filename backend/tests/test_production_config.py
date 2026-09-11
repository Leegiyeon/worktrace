import pytest

from app.core.config import Settings, validate_runtime_settings


def test_production_rejects_local_defaults() -> None:
    with pytest.raises(RuntimeError, match="Invalid production settings"):
        validate_runtime_settings(Settings(
            app_env="production",
            postgres_password=None,
            default_owner_id="local-owner",
            report_access_token="dev-only-report-token",
            frontend_origin="http://localhost:3000",
        ))


def test_production_accepts_explicit_secure_settings() -> None:
    settings = Settings(
        app_env="production",
        postgres_password="database-secret",
        default_owner_id="personal-owner-42",
        report_access_token="internal-token-42",
        frontend_origin="https://work.example.com",
    )

    validate_runtime_settings(settings)
