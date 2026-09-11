import json

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.errors import http_error
from app.core.config import Settings, get_settings
from app.services.github_webhooks import (
    GitHubWebhookNotConfiguredError,
    GitHubWebhookSignatureError,
    ingest_github_event,
    verify_github_signature,
)

router = APIRouter(prefix="/webhooks/github", tags=["github-webhooks"])


@router.post("")
async def receive_github_webhook(
    request: Request,
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, str | int]:
    if not x_github_delivery or not x_github_event:
        raise http_error(status.HTTP_400_BAD_REQUEST, "GITHUB_HEADERS_REQUIRED", "GitHub delivery headers are required.")
    body = await request.body()
    try:
        verify_github_signature(settings, body, x_hub_signature_256)
    except GitHubWebhookNotConfiguredError as exc:
        raise http_error(status.HTTP_503_SERVICE_UNAVAILABLE, "GITHUB_WEBHOOK_NOT_CONFIGURED", "GitHub webhook secret is not configured.") from exc
    except GitHubWebhookSignatureError as exc:
        raise http_error(status.HTTP_403_FORBIDDEN, "GITHUB_SIGNATURE_INVALID", "GitHub webhook signature is invalid.") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise http_error(status.HTTP_400_BAD_REQUEST, "GITHUB_PAYLOAD_INVALID", "GitHub webhook payload is invalid JSON.") from exc
    result = ingest_github_event(settings, x_github_delivery, x_github_event, payload)
    return {"status": result.status, "reason": result.reason, "commits_stored": result.commits_stored}
