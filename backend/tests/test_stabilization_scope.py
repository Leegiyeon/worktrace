from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_progress_scope_adds_projects_but_keeps_excluded_routes_out() -> None:
    paths = {route.path for route in app.routes}

    assert "/projects" in paths
    assert "/projects/{project_id}/tasks" in paths
    assert not any(path.startswith("/documents") for path in paths)
    assert not any(path.startswith("/uploads") for path in paths)
    assert not any(path.startswith("/rag") for path in paths)


def test_readme_documents_stabilization_runtime_contracts() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    root_env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    backend_env = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    frontend_env = (REPO_ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for key in [
        "REPORT_ACCESS_TOKEN",
        "DEFAULT_OWNER_ID",
        "REPORT_TIMEZONE",
        "NEXT_PUBLIC_WORKTRACE_OWNER_ID",
        "WORKTRACE_OWNER_ID",
        "WORKTRACE_REPORT_TOKEN",
    ]:
        assert key in readme
        assert key in root_env or key in backend_env or key in frontend_env
        assert key in compose or key in root_env

    assert "NEXT_PUBLIC_WORKTRACE_REPORT_TOKEN" not in root_env
    assert "NEXT_PUBLIC_WORKTRACE_REPORT_TOKEN" not in frontend_env
    assert "NEXT_PUBLIC_WORKTRACE_REPORT_TOKEN" not in compose
    assert "canonical SQL" in readme
    assert "{code, message}" in readme
