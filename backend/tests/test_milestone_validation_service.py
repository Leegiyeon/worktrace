from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.milestone_evidence as service
from app.schemas.milestone_evidence import MilestoneEvidenceSummary


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, substantive_pending: int, criteria: str = "검증 기준"):
        self.substantive_pending = substantive_pending
        self.criteria = criteria
        self.updated_status = None

    def execute(self, query, params):
        normalized = " ".join(query.split())
        if "SELECT id FROM projects" in normalized:
            return FakeResult({"id": params[1]})
        if "set_config(" in normalized:
            return FakeResult(None)
        if "FROM project_milestones" in normalized:
            return FakeResult({"id": params[2], "acceptance_criteria": self.criteria})
        if "SELECT id FROM project_tasks" in normalized:
            return FakeResult({"id": uuid4()})
        if "SELECT COUNT(*)::int AS total" in normalized:
            return FakeResult({"total": self.substantive_pending})
        if "UPDATE project_tasks" in normalized:
            self.updated_status = params[0]
            return FakeResult(None)
        if "UPDATE projects" in normalized:
            return FakeResult(None)
        raise AssertionError(normalized)


def test_missing_project_preserves_milestone_not_found_error(monkeypatch):
    @contextmanager
    def fake_connect(settings):
        yield FakeConnection(0)

    def missing(*args):
        raise service.ProjectNotFoundError()

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "_lock_project_for_write", missing)
    with pytest.raises(service.ProjectMilestoneNotFoundError):
        service.update_milestone_validation_status(SimpleNamespace(), "owner", uuid4(), uuid4(), "done")


def test_validation_completion_is_blocked_while_real_wbs_remains(monkeypatch) -> None:
    connection = FakeConnection(substantive_pending=1)

    @contextmanager
    def fake_connect(settings):
        yield connection

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "latest_review_allows_completion", lambda *args: True)

    with pytest.raises(service.MilestoneValidationBlockedError):
        service.update_milestone_validation_status(
            SimpleNamespace(), "owner", uuid4(), uuid4(), "done"
        )

    assert connection.updated_status is None


def test_validation_completion_is_blocked_without_current_ready_review(monkeypatch) -> None:
    connection = FakeConnection(substantive_pending=0)

    @contextmanager
    def fake_connect(settings):
        yield connection

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "latest_review_allows_completion", lambda *args: False)

    with pytest.raises(service.MilestoneValidationBlockedError):
        service.update_milestone_validation_status(
            SimpleNamespace(), "owner", uuid4(), uuid4(), "done"
        )

    assert connection.updated_status is None


def test_validation_completion_updates_only_validation_checkpoint(monkeypatch) -> None:
    connection = FakeConnection(substantive_pending=0)
    expected = MilestoneEvidenceSummary(milestone_id=str(uuid4()), total_wbs=2, completed_wbs=2)

    @contextmanager
    def fake_connect(settings):
        yield connection

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "latest_review_allows_completion", lambda *args: True)
    monkeypatch.setattr(service, "get_milestone_evidence", lambda *args: expected)

    result = service.update_milestone_validation_status(
        SimpleNamespace(), "owner", uuid4(), uuid4(), "done"
    )

    assert connection.updated_status == "done"
    assert result is expected


def test_validation_can_be_reopened_without_completion_gate(monkeypatch) -> None:
    connection = FakeConnection(substantive_pending=5, criteria="")
    expected = MilestoneEvidenceSummary(milestone_id=str(uuid4()), total_wbs=2, completed_wbs=1)

    @contextmanager
    def fake_connect(settings):
        yield connection

    monkeypatch.setattr(service, "connect", fake_connect)
    monkeypatch.setattr(service, "get_milestone_evidence", lambda *args: expected)

    result = service.update_milestone_validation_status(
        SimpleNamespace(), "owner", uuid4(), uuid4(), "planned"
    )

    assert connection.updated_status == "planned"
    assert result is expected
