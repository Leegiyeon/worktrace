import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.api import github_webhooks
from app.core.config import get_settings
from app.main import app
from app.services.github_webhooks import GitHubWebhookResult


def _signed_headers(body: bytes, secret: str, **overrides: str) -> dict[str, str]:
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-GitHub-Delivery": "delivery-1",
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    }
    headers.update(overrides)
    return headers


def test_github_webhook_verifies_signature_and_ingests(monkeypatch):
    settings = get_settings()
    previous_secret = settings.github_webhook_secret
    settings.github_webhook_secret = "webhook-secret"
    calls = []

    def fake_ingest(current_settings, delivery_id, event_name, payload):
        calls.append((delivery_id, event_name, payload["ref"]))
        return GitHubWebhookResult(status="processed", reason="", commits_stored=2)

    monkeypatch.setattr(github_webhooks, "ingest_github_event", fake_ingest)
    body = json.dumps({"ref": "refs/heads/main", "repository": {"id": 1}, "commits": []}).encode()
    try:
        response = TestClient(app).post("/webhooks/github", content=body, headers=_signed_headers(body, "webhook-secret"))
    finally:
        settings.github_webhook_secret = previous_secret

    assert response.status_code == 200
    assert response.json() == {"status": "processed", "reason": "", "commits_stored": 2}
    assert calls == [("delivery-1", "push", "refs/heads/main")]


def test_github_webhook_rejects_invalid_signature():
    settings = get_settings()
    previous_secret = settings.github_webhook_secret
    settings.github_webhook_secret = "webhook-secret"
    body = b'{"ref":"refs/heads/main"}'
    try:
        response = TestClient(app).post(
            "/webhooks/github",
            content=body,
            headers=_signed_headers(body, "wrong-secret"),
        )
    finally:
        settings.github_webhook_secret = previous_secret

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "GITHUB_SIGNATURE_INVALID"


def test_github_webhook_requires_delivery_headers():
    response = TestClient(app).post("/webhooks/github", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "GITHUB_HEADERS_REQUIRED"
