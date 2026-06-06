from functools import lru_cache
from typing import Optional
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the skeleton API.

    The MVP stores files locally first. Upload, AI analysis, and authentication
    are intentionally out of scope for this initial scaffold.
    """

    app_name: str = "work-support API"
    app_env: str = "local"
    database_url: Optional[str] = None
    postgres_db: str = "work_support"
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
