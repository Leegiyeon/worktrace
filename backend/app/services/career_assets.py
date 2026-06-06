from uuid import UUID

from app.core.config import Settings
from app.db.connection import connect
from app.schemas.career_assets import CareerAsset, CareerTargetRole


class CareerAssetProjectNotFoundError(Exception):
    pass


def list_project_career_assets(settings: Settings, owner_id: str, project_id: UUID) -> list[CareerAsset]:
    with connect(settings) as connection:
        project = connection.execute(
            "SELECT id FROM projects WHERE owner_id = %(owner_id)s AND id = %(project_id)s",
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
        if project is None:
            raise CareerAssetProjectNotFoundError()
        rows = connection.execute(
            """
            SELECT id::text,
                   project_id::text,
                   source_summary,
                   work_summary,
                   outcome_summary,
                   resume_bullets,
                   career_description,
                   portfolio_description,
                   star_answer,
                   markdown,
                   generation_method,
                   created_at::text,
                   updated_at::text
            FROM career_assets
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s
            ORDER BY updated_at DESC, created_at DESC
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()
    return [_career_asset_from_row(row) for row in rows]


def generate_project_career_asset(
    settings: Settings,
    owner_id: str,
    project_id: UUID,
    target_role: CareerTargetRole,
) -> CareerAsset:
    with connect(settings) as connection:
        project = connection.execute(
            """
            SELECT id::text, title, description, status, role
            FROM projects
            WHERE owner_id = %(owner_id)s AND id = %(project_id)s
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchone()
        if project is None:
            raise CareerAssetProjectNotFoundError()

        tasks = connection.execute(
            """
            SELECT id::text, title, description, status, priority, due_date::text, updated_at::text
            FROM project_tasks
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s
            ORDER BY
              CASE status WHEN 'done' THEN 1 WHEN 'in_progress' THEN 2 WHEN 'planned' THEN 3 ELSE 4 END,
              updated_at DESC,
              title ASC
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()
        work_logs = connection.execute(
            """
            SELECT id::text, log_date::text, work_type, title, content, decisions,
                   collaborators, next_actions, duration_minutes, blockers, updated_at::text
            FROM work_logs
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s
            ORDER BY log_date DESC, updated_at DESC
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()
        outcomes = connection.execute(
            """
            SELECT id::text, title, outcome_type, before_state, after_state,
                   metric_name, metric_value::text, metric_unit,
                   evidence_work_log_ids, resume_ready, updated_at::text
            FROM project_outcomes
            WHERE owner_id = %(owner_id)s AND project_id = %(project_id)s
            ORDER BY resume_ready DESC, updated_at DESC, title ASC
            """,
            {"owner_id": owner_id, "project_id": project_id},
        ).fetchall()

        generated = _build_career_asset_content(project, tasks, work_logs, outcomes, target_role)
        row = connection.execute(
            """
            INSERT INTO career_assets (
                owner_id,
                project_id,
                source_summary,
                work_summary,
                outcome_summary,
                resume_bullets,
                career_description,
                portfolio_description,
                star_answer,
                markdown,
                generation_method
            )
            VALUES (
                %(owner_id)s,
                %(project_id)s,
                %(source_summary)s,
                %(work_summary)s,
                %(outcome_summary)s,
                %(resume_bullets)s,
                %(career_description)s,
                %(portfolio_description)s,
                %(star_answer)s,
                %(markdown)s,
                %(generation_method)s
            )
            RETURNING id::text,
                      project_id::text,
                      source_summary,
                      work_summary,
                      outcome_summary,
                      resume_bullets,
                      career_description,
                      portfolio_description,
                      star_answer,
                      markdown,
                      generation_method,
                      created_at::text,
                      updated_at::text
            """,
            {
                "owner_id": owner_id,
                "project_id": project_id,
                **generated,
            },
        ).fetchone()

    return _career_asset_from_row(row)


def _career_asset_from_row(row) -> CareerAsset:
    return CareerAsset(
        id=row["id"],
        project_id=row["project_id"],
        source_summary=row.get("source_summary") or "",
        work_summary=row.get("work_summary") or "",
        outcome_summary=row.get("outcome_summary") or "",
        resume_bullets=row.get("resume_bullets") or "",
        career_description=row.get("career_description") or "",
        portfolio_description=row.get("portfolio_description") or "",
        star_answer=row.get("star_answer") or "",
        markdown=row.get("markdown") or "",
        generation_method=row.get("generation_method") or "template",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _build_career_asset_content(project, tasks, work_logs, outcomes, target_role: CareerTargetRole) -> dict[str, str]:
    preferred_outcomes = _preferred_outcomes(outcomes)
    weak_evidence = _has_weak_evidence(work_logs, outcomes, preferred_outcomes)
    prefix = "[초안] " if weak_evidence else ""
    generation_method = f"template_draft:{target_role}" if weak_evidence else f"template:{target_role}"

    source_summary = _source_summary(project, tasks, work_logs, outcomes, target_role, weak_evidence)
    work_summary = _work_summary(project, tasks, work_logs, prefix)
    outcome_summary = _outcome_summary(preferred_outcomes, prefix)
    resume_bullets = _resume_bullets(project, target_role, preferred_outcomes, tasks, work_logs, prefix)
    career_description = _career_description(project, target_role, work_summary, outcome_summary, prefix)
    portfolio_description = _portfolio_description(project, target_role, preferred_outcomes, work_logs, prefix)
    star_answer = _star_answer(project, target_role, tasks, work_logs, preferred_outcomes, prefix)
    markdown = _markdown(
        project,
        target_role,
        source_summary,
        work_summary,
        outcome_summary,
        resume_bullets,
        career_description,
        portfolio_description,
        star_answer,
    )

    return {
        "source_summary": source_summary,
        "work_summary": work_summary,
        "outcome_summary": outcome_summary,
        "resume_bullets": resume_bullets,
        "career_description": career_description,
        "portfolio_description": portfolio_description,
        "star_answer": star_answer,
        "markdown": markdown,
        "generation_method": generation_method,
    }


def _preferred_outcomes(outcomes) -> list:
    resume_ready = [outcome for outcome in outcomes if outcome.get("resume_ready")]
    return resume_ready if resume_ready else list(outcomes)


def _has_weak_evidence(work_logs, outcomes, preferred_outcomes) -> bool:
    if not work_logs or not outcomes:
        return True
    if not any(outcome.get("resume_ready") for outcome in outcomes):
        return True
    return not any(outcome.get("evidence_work_log_ids") for outcome in preferred_outcomes)


def _source_summary(project, tasks, work_logs, outcomes, target_role: CareerTargetRole, weak_evidence: bool) -> str:
    status = "초안" if weak_evidence else "확정 근거 기반"
    return (
        f"{project['title']} · 목표 역할 {target_role} · 프로젝트 상태 {project.get('status') or '-'} · "
        f"업무 {len(tasks)}건 · 업무 로그 {len(work_logs)}건 · 성과 {len(outcomes)}건 · {status}"
    )


def _work_summary(project, tasks, work_logs, prefix: str) -> str:
    done_tasks = [task["title"] for task in tasks if task.get("status") == "done"][:3]
    recent_logs = [log["title"] for log in work_logs[:3]]
    parts = []
    if done_tasks:
        parts.append(f"완료 업무: {', '.join(done_tasks)}")
    if recent_logs:
        parts.append(f"주요 로그: {', '.join(recent_logs)}")
    if not parts:
        parts.append(f"{project['title']}의 저장된 업무 근거가 부족합니다.")
    return prefix + " / ".join(parts)


def _outcome_summary(outcomes, prefix: str) -> str:
    if not outcomes:
        return prefix + "확인된 성과가 없어 업무 로그와 완료 업무 보강이 필요합니다."
    return prefix + " / ".join(_outcome_phrase(outcome) for outcome in outcomes[:3])


def _resume_bullets(project, target_role: CareerTargetRole, outcomes, tasks, work_logs, prefix: str) -> str:
    project_title = project["title"]
    first_work = _first_title([task for task in tasks if task.get("status") == "done"]) or _first_title(work_logs) or "프로젝트 업무"
    bullets = [
        f"- {prefix}{target_role} 관점에서 {project_title}의 {first_work} 흐름을 정리하고 실행 근거를 업무 로그로 축적",
    ]
    if outcomes:
        bullets.append(f"- {prefix}{_outcome_phrase(outcomes[0])}")
    else:
        bullets.append(f"- {prefix}성과 수치와 이력서 반영 여부는 사용자 확인 후 보강 예정")
    return "\n".join(bullets)


def _career_description(project, target_role: CareerTargetRole, work_summary: str, outcome_summary: str, prefix: str) -> str:
    return (
        f"{prefix}{target_role} 역할을 목표로 {project['title']} 프로젝트에서 {work_summary}를 수행했습니다. "
        f"성과는 {outcome_summary} 기준으로 정리했으며, 저장된 업무 로그와 사용자가 확정한 성과만 반영했습니다."
    )


def _portfolio_description(project, target_role: CareerTargetRole, outcomes, work_logs, prefix: str) -> str:
    evidence = f"업무 로그 {len(work_logs)}건"
    outcome_text = _outcome_phrase(outcomes[0]) if outcomes else "성과 확인 전"
    return (
        f"{prefix}{project['title']}는 {target_role} 포트폴리오 관점에서 프로젝트 맥락, 실행 기록, 성과 근거를 연결한 사례입니다. "
        f"{evidence}과 확인된 성과({outcome_text})를 바탕으로 설명합니다."
    )


def _star_answer(project, target_role: CareerTargetRole, tasks, work_logs, outcomes, prefix: str) -> str:
    task_text = _first_title(tasks) or "업무 범위 정리"
    action_text = _first_title(work_logs) or "업무 기록 정리"
    result_text = _outcome_phrase(outcomes[0]) if outcomes else "사용자 확인 성과 보강 필요"
    return "\n".join(
        [
            f"Situation: {prefix}{project['title']}에서 프로젝트 진행 기록과 성과 근거를 정리해야 했습니다.",
            f"Task: {target_role} 관점에서 {task_text}를 수행하고 재사용 가능한 경력 소재로 정리해야 했습니다.",
            f"Action: {action_text} 등 저장된 업무 로그를 기준으로 수행 내용과 결정/다음 액션을 연결했습니다.",
            f"Result: {result_text}",
        ]
    )


def _markdown(
    project,
    target_role: CareerTargetRole,
    source_summary: str,
    work_summary: str,
    outcome_summary: str,
    resume_bullets: str,
    career_description: str,
    portfolio_description: str,
    star_answer: str,
) -> str:
    return "\n\n".join(
        [
            f"# {project['title']} 경력 자산 ({target_role})",
            f"## 근거\n{source_summary}",
            f"## 업무 요약\n{work_summary}",
            f"## 성과 요약\n{outcome_summary}",
            f"## 이력서 bullet\n{resume_bullets}",
            f"## 경력기술서\n{career_description}",
            f"## 포트폴리오\n{portfolio_description}",
            f"## STAR\n{star_answer}",
        ]
    )


def _outcome_phrase(outcome) -> str:
    metric = _metric_text(outcome)
    base = outcome["title"]
    if metric:
        return f"{base} ({metric})"
    if outcome.get("after_state"):
        return f"{base}: {outcome['after_state']}"
    return base


def _metric_text(outcome) -> str:
    if not outcome.get("metric_value"):
        return ""
    name = outcome.get("metric_name") or "확정 수치"
    unit = outcome.get("metric_unit") or ""
    return f"{name} {outcome['metric_value']}{unit}"


def _first_title(rows) -> str:
    if not rows:
        return ""
    return rows[0].get("title") or ""
