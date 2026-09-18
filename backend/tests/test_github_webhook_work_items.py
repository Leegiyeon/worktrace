from datetime import date

from app.services.github_webhooks import _sync_commit_work_items


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        if "string_agg" in query:
            return Result({"log_date": date(2026, 9, 11), "commit_count": 2, "content": "- first\n- second"})
        return Result()


def test_commit_creates_only_an_insert_only_daily_work_log():
    connection = Connection()

    _sync_commit_work_items(
        connection,
        "owner-id",
        "source-id",
        "project-id",
        "abcdef123456",
        {
            "message": "Ship usable GitHub data\n\nDetails",
            "timestamp": "2026-09-11T01:02:03Z",
            "url": "https://github.com/example/repo/commit/abcdef123456",
        },
    )

    assert len(connection.calls) == 2
    assert all("project_tasks" not in query for query, _ in connection.calls)
    assert "repository_source_id = %(source_id)s" in connection.calls[0][0]
    log_query, log_params = connection.calls[1]
    assert "INSERT INTO work_logs" in log_query
    assert "DO NOTHING" in log_query
    assert "DO UPDATE" not in log_query
    assert log_params["title"] == "GitHub 작업 · 2개 커밋"
    assert log_params["source_key"] == "day:source-id:2026-09-11"


def test_commit_without_timestamp_does_not_invent_work():
    connection = Connection()

    _sync_commit_work_items(connection, "owner-id", "source-id", "project-id", "abc", {"message": ""})

    assert connection.calls == []
