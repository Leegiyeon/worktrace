-- Synthesize milestone-scoped WBS from commit evidence only when a project has no real GitHub Issue WBS.
-- Raw commits remain evidence; this migration creates one implementation summary task per evidenced milestone
-- plus one user-verifiable acceptance task so commit history alone can never make a milestone 100% complete.

CREATE OR REPLACE FUNCTION worktrace_refresh_commit_derived_wbs(p_owner_id TEXT, p_project_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM project_tasks t
        WHERE t.owner_id = p_owner_id
          AND t.project_id = p_project_id
          AND t.source_provider = 'github'
          AND t.source_key LIKE 'issue:%'
    ) THEN
        DELETE FROM project_tasks
        WHERE owner_id = p_owner_id
          AND project_id = p_project_id
          AND source_provider = 'derived-github'
          AND (source_key LIKE 'commit-milestone:%' OR source_key LIKE 'milestone-validation:%');
        RETURN;
    END IF;

    INSERT INTO project_tasks (
        owner_id,
        project_id,
        title,
        description,
        status,
        priority,
        source_provider,
        source_key,
        milestone_id,
        counts_toward_progress
    )
    SELECT
        e.owner_id,
        e.project_id,
        '[커밋 근거] ' || m.title || ' 구현',
        format(
            'main 브랜치의 분류된 커밋 %s건을 근거로 합성한 구현 WBS입니다. 개별 커밋은 Evidence로 유지되며 이 행은 기능군 요약입니다.',
            COUNT(*)
        ),
        'done',
        'medium',
        'derived-github',
        'commit-milestone:' || m.id::text,
        m.id,
        true
    FROM project_milestone_evidence e
    JOIN project_milestones m
      ON m.id = e.milestone_id
     AND m.owner_id = e.owner_id
     AND m.project_id = e.project_id
    WHERE e.owner_id = p_owner_id
      AND e.project_id = p_project_id
    GROUP BY e.owner_id, e.project_id, m.id, m.title
    ON CONFLICT (owner_id, source_provider, source_key)
        WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
    DO UPDATE SET
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        status = 'done',
        milestone_id = EXCLUDED.milestone_id,
        counts_toward_progress = true,
        updated_at = now();

    INSERT INTO project_tasks (
        owner_id,
        project_id,
        title,
        description,
        status,
        priority,
        source_provider,
        source_key,
        milestone_id,
        counts_toward_progress
    )
    SELECT DISTINCT
        e.owner_id,
        e.project_id,
        '[검증 필요] ' || m.title || ' 성취 기준 확인',
        CASE
            WHEN btrim(COALESCE(m.acceptance_criteria, '')) <> '' THEN m.acceptance_criteria
            ELSE '커밋 근거만으로 완료를 확정하지 말고 실제 동작과 사용자 기준을 확인한다.'
        END,
        'planned',
        'medium',
        'derived-github',
        'milestone-validation:' || m.id::text,
        m.id,
        true
    FROM project_milestone_evidence e
    JOIN project_milestones m
      ON m.id = e.milestone_id
     AND m.owner_id = e.owner_id
     AND m.project_id = e.project_id
    WHERE e.owner_id = p_owner_id
      AND e.project_id = p_project_id
    ON CONFLICT (owner_id, source_provider, source_key)
        WHERE source_provider IS NOT NULL AND source_key IS NOT NULL
    DO UPDATE SET
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        milestone_id = EXCLUDED.milestone_id,
        counts_toward_progress = true,
        updated_at = now();
END;
$$;

CREATE OR REPLACE FUNCTION worktrace_refresh_commit_derived_wbs_from_evidence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM worktrace_refresh_commit_derived_wbs(
        COALESCE(NEW.owner_id, OLD.owner_id),
        COALESCE(NEW.project_id, OLD.project_id)
    );
    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_refresh_commit_derived_wbs_evidence ON project_milestone_evidence;
CREATE TRIGGER trg_refresh_commit_derived_wbs_evidence
AFTER INSERT OR DELETE ON project_milestone_evidence
FOR EACH ROW
EXECUTE FUNCTION worktrace_refresh_commit_derived_wbs_from_evidence();

CREATE OR REPLACE FUNCTION worktrace_refresh_commit_derived_wbs_from_issue()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    changed_provider TEXT;
    changed_key TEXT;
    changed_owner TEXT;
    changed_project UUID;
BEGIN
    changed_provider := COALESCE(NEW.source_provider, OLD.source_provider);
    changed_key := COALESCE(NEW.source_key, OLD.source_key);
    changed_owner := COALESCE(NEW.owner_id, OLD.owner_id);
    changed_project := COALESCE(NEW.project_id, OLD.project_id);

    IF changed_provider = 'github' AND changed_key LIKE 'issue:%' THEN
        PERFORM worktrace_refresh_commit_derived_wbs(changed_owner, changed_project);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_refresh_commit_derived_wbs_issue ON project_tasks;
CREATE TRIGGER trg_refresh_commit_derived_wbs_issue
AFTER INSERT OR UPDATE OR DELETE ON project_tasks
FOR EACH ROW
WHEN (
    COALESCE(NEW.source_provider, OLD.source_provider) = 'github'
    AND COALESCE(NEW.source_key, OLD.source_key) LIKE 'issue:%'
)
EXECUTE FUNCTION worktrace_refresh_commit_derived_wbs_from_issue();

DO $$
DECLARE
    project_row RECORD;
BEGIN
    FOR project_row IN
        SELECT DISTINCT owner_id, project_id
        FROM project_milestone_evidence
    LOOP
        PERFORM worktrace_refresh_commit_derived_wbs(project_row.owner_id, project_row.project_id);
    END LOOP;
END;
$$;
