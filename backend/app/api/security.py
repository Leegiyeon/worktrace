from dataclasses import dataclass
from secrets import compare_digest

from fastapi import Depends, Header, status

from app.api.errors import http_error
from app.core.config import Settings, get_settings


REPORT_TOKEN_NOT_CONFIGURED = "REPORT_TOKEN_NOT_CONFIGURED"
REPORT_DEFAULT_TOKEN_NOT_ALLOWED = "REPORT_DEFAULT_TOKEN_NOT_ALLOWED"
REPORT_ACCESS_HEADERS_REQUIRED = "REPORT_ACCESS_HEADERS_REQUIRED"
REPORT_OWNER_FORBIDDEN = "REPORT_OWNER_FORBIDDEN"
REPORT_TOKEN_INVALID = "REPORT_TOKEN_INVALID"


@dataclass(frozen=True)
class OwnerContext:
    owner_id: str


def require_owner_context(
    x_worktrace_owner_id: str | None = Header(default=None),
    x_worktrace_report_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> OwnerContext:
    """Validate the local personal-MVP owner guard and return owner context.

    This is not a login system. It prevents unauthenticated browser/API calls from
    dumping all locally stored work records until a real auth layer is added.
    """

    if not settings.report_access_token:
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            REPORT_TOKEN_NOT_CONFIGURED,
            "Report access token is not configured.",
        )

    if settings.app_env != "local" and settings.report_access_token == "dev-only-report-token":
        raise http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            REPORT_DEFAULT_TOKEN_NOT_ALLOWED,
            "Default report access token cannot be used outside local development.",
        )

    if not x_worktrace_owner_id or not x_worktrace_report_token:
        raise http_error(
            status.HTTP_401_UNAUTHORIZED,
            REPORT_ACCESS_HEADERS_REQUIRED,
            "Report access headers are required.",
        )

    if x_worktrace_owner_id != settings.default_owner_id:
        raise http_error(
            status.HTTP_403_FORBIDDEN,
            REPORT_OWNER_FORBIDDEN,
            "Report owner is not allowed.",
        )

    if not compare_digest(x_worktrace_report_token, settings.report_access_token):
        raise http_error(
            status.HTTP_401_UNAUTHORIZED,
            REPORT_TOKEN_INVALID,
            "Report access token is invalid.",
        )

    return OwnerContext(owner_id=x_worktrace_owner_id)


def require_report_access(
    x_worktrace_owner_id: str | None = Header(default=None),
    x_worktrace_report_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Backward-compatible report dependency returning the validated owner id."""

    return require_owner_context(x_worktrace_owner_id, x_worktrace_report_token, settings).owner_id
