from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import app.services.milestone_review_state as state


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def execute(self, query, params):
        return FakeResult(self.row)


def test_latest_ready_review_with_matching_context_allows_completion(monkeypatch) -> None:
    @contextmanager
    def fake_connect(settings):
        yield FakeConnection({"verdict": "ready_candidate", "context_fingerprint": "same"})

    monkeypatch.setattr(state, "connect", fake_connect)
    monkeypatch.setattr(state, "build_milestone_review_context_fingerprint", lambda *args: "same")

    assert state.latest_review_allows_completion(SimpleNamespace(), "owner", uuid4(), uuid4()) is True


def test_stale_ready_review_does_not_allow_completion(monkeypatch) -> None:
    @contextmanager
    def fake_connect(settings):
        yield FakeConnection({"verdict": "ready_candidate", "context_fingerprint": "old"})

    monkeypatch.setattr(state, "connect", fake_connect)
    monkeypatch.setattr(state, "build_milestone_review_context_fingerprint", lambda *args: "new")

    assert state.latest_review_allows_completion(SimpleNamespace(), "owner", uuid4(), uuid4()) is False


def test_current_non_ready_review_does_not_allow_completion(monkeypatch) -> None:
    @contextmanager
    def fake_connect(settings):
        yield FakeConnection({"verdict": "needs_review", "context_fingerprint": "same"})

    monkeypatch.setattr(state, "connect", fake_connect)
    monkeypatch.setattr(state, "build_milestone_review_context_fingerprint", lambda *args: "same")

    assert state.latest_review_allows_completion(SimpleNamespace(), "owner", uuid4(), uuid4()) is False
