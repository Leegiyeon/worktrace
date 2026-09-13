from functools import lru_cache
from typing import Optional
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the skeleton API.

    The current MVP manages local work evidence and career assets. File ingestion,
    document analysis, RAG, and authentication remain outside this slice.
    """

    app_name: str = "worktrace API"
    app_env: str = "local"
    database_url: Optional[str] = None
    postgres_db: str = "worktrace"
    postgres_user: str = "leegiyeon"
    postgres_password: Optional[str] = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    local_storage_root: str = "storage/uploads"
    frontend_origin: str = "http://localhost:3000"
    default_owner_id: str = "local-owner"
    report_access_token: str = "dev-only-report-token"
    report_timezone: str = "Asia/Seoul"
    work_support_schema_sql_path: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    github_sync_token: Optional[str] = None
    github_webhook_secret: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        """Build the DB URL from env-backed settings without hardcoding secrets."""

        if self.database_url:
            return self.database_url
        if not self.postgres_password:
            raise ValueError("POSTGRES_PASSWORD is required in the local environment.")

        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        database = quote(self.postgres_db, safe="")
        return f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{database}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_runtime_settings(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    errors = []
    if not settings.postgres_password:
        errors.append("POSTGRES_PASSWORD")
    if not settings.report_access_token or settings.report_access_token == "dev-only-report-token":
        errors.append("REPORT_ACCESS_TOKEN")
    if not settings.default_owner_id or settings.default_owner_id == "local-owner":
        errors.append("DEFAULT_OWNER_ID")
    if not settings.frontend_origin.startswith("https://"):
        errors.append("FRONTEND_ORIGIN must use https")
    if not settings.github_webhook_secret:
        errors.append("GITHUB_WEBHOOK_SECRET")
    if errors:
        raise RuntimeError("Invalid production settings: " + ", ".join(errors))
