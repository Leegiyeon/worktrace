import os

from app.core.config import Settings


# Tests must not load developer secrets from a repository .env file.
Settings.model_config = {**Settings.model_config, "env_file": None}


os.environ["APP_ENV"] = "local"
os.environ["DEFAULT_OWNER_ID"] = "local-owner"
os.environ["REPORT_ACCESS_TOKEN"] = "dev-only-report-token"
os.environ["DATABASE_URL"] = "postgresql://example"
