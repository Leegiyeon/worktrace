-- GitHub commits and pull requests are evidence of work, not planned WBS.
-- Keep canonical evidence in github_commits/work_logs and exclude these rows from project_tasks.
DELETE FROM project_tasks
WHERE source_provider = 'github'
  AND (source_key LIKE 'commit:%' OR source_key LIKE 'pr:%');

CREATE OR REPLACE FUNCTION worktrace_skip_github_evidence_task()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.source_provider = 'github'
       AND (NEW.source_key LIKE 'commit:%' OR NEW.source_key LIKE 'pr:%') THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_skip_github_evidence_task ON project_tasks;
CREATE TRIGGER trg_skip_github_evidence_task
BEFORE INSERT OR UPDATE ON project_tasks
FOR EACH ROW
EXECUTE FUNCTION worktrace_skip_github_evidence_task();
