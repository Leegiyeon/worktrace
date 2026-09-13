-- Canonicalize Worktrace commit evidence with specific milestone signals before broad project/WBS terms.
-- The GitHub sync remains the first-pass classifier, while this database boundary prevents generic words
-- such as "project" or "evidence" from stealing commits that clearly belong to another milestone.

CREATE OR REPLACE FUNCTION worktrace_infer_worktrace_milestone_key(p_message TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    normalized TEXT := lower(COALESCE(p_message, ''));
BEGIN
    -- Specific product capabilities first. Avoid broad "project" and "evidence" signals.
    IF normalized ~ '(project[ _-]?(analyst|insight)|analyst|insight|blocker|next[ _-]?action|priority|우선순위|프로젝트 분석)' THEN
        RETURN 'project-insight';
    END IF;
    IF normalized ~ '(work[ _-]?(capture|log)|업무[ _-]?로그|업무 기록|capture)' THEN
        RETURN 'work-capture';
    END IF;
    IF normalized ~ '(outcome|성과 후보|성과)' THEN
        RETURN 'outcome';
    END IF;
    IF normalized ~ '(career|resume|star|portfolio|경력|이력서|포트폴리오)' THEN
        RETURN 'career-ai';
    END IF;
    IF normalized ~ '(work[ _-]?memory|memory|rag|vector|embedding|semantic[ _-]?search|의미 검색|기억)' THEN
        RETURN 'work-memory';
    END IF;
    IF normalized ~ '(\mwbs\M|milestone|마일스톤|progress|진척|goal|목표·마일스톤|목표 관리)' THEN
        RETURN 'project-wbs';
    END IF;
    IF normalized ~ '(github|webhook|github[ _-]?commit|commit[ _-]?(sync|import|history)|커밋[ _-]?(동기화|수집)|repository[ _-]?(sync|evidence)|repo[ _-]?(sync|evidence))' THEN
        RETURN 'github-evidence';
    END IF;
    IF normalized ~ '(deploy|배포|oracle|https|auth|인증|backup|백업|복구|docker|ci/cd|migration)' THEN
        RETURN 'operations';
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION worktrace_canonicalize_worktrace_evidence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    project_title TEXT;
    commit_message TEXT;
    preferred_key TEXT;
    preferred_milestone UUID;
BEGIN
    SELECT p.title, c.message
      INTO project_title, commit_message
      FROM projects p
      JOIN github_commits c
        ON c.id = NEW.github_commit_id
       AND c.owner_id = NEW.owner_id
       AND c.project_id = NEW.project_id
     WHERE p.id = NEW.project_id
       AND p.owner_id = NEW.owner_id;

    IF lower(COALESCE(project_title, '')) <> 'worktrace' THEN
        RETURN NEW;
    END IF;

    preferred_key := worktrace_infer_worktrace_milestone_key(commit_message);
    IF preferred_key IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT id
      INTO preferred_milestone
      FROM project_milestones
     WHERE owner_id = NEW.owner_id
       AND project_id = NEW.project_id
       AND milestone_key = preferred_key;

    IF preferred_milestone IS NOT NULL THEN
        NEW.milestone_id := preferred_milestone;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_canonicalize_worktrace_evidence ON project_milestone_evidence;
CREATE TRIGGER trg_canonicalize_worktrace_evidence
BEFORE INSERT OR UPDATE ON project_milestone_evidence
FOR EACH ROW
EXECUTE FUNCTION worktrace_canonicalize_worktrace_evidence();

-- Reclassify historical Worktrace evidence. Delete the wrong link first to avoid the evidence PK
-- conflicting when the preferred link already exists, then insert the canonical link idempotently.
DO $$
DECLARE
    project_row RECORD;
BEGIN
    FOR project_row IN
        SELECT p.owner_id, p.id AS project_id
          FROM projects p
         WHERE lower(p.title) = 'worktrace'
    LOOP
        CREATE TEMP TABLE IF NOT EXISTS _worktrace_evidence_reclassify (
            owner_id TEXT,
            project_id UUID,
            github_commit_id UUID,
            milestone_key TEXT,
            confidence TEXT
        ) ON COMMIT DROP;
        TRUNCATE _worktrace_evidence_reclassify;

        INSERT INTO _worktrace_evidence_reclassify(owner_id, project_id, github_commit_id, milestone_key, confidence)
        SELECT e.owner_id,
               e.project_id,
               e.github_commit_id,
               worktrace_infer_worktrace_milestone_key(c.message),
               e.confidence
          FROM project_milestone_evidence e
          JOIN github_commits c ON c.id = e.github_commit_id
         WHERE e.owner_id = project_row.owner_id
           AND e.project_id = project_row.project_id
           AND worktrace_infer_worktrace_milestone_key(c.message) IS NOT NULL;

        DELETE FROM project_milestone_evidence e
         USING _worktrace_evidence_reclassify r
         WHERE e.owner_id = r.owner_id
           AND e.project_id = r.project_id
           AND e.github_commit_id = r.github_commit_id;

        INSERT INTO project_milestone_evidence(owner_id, project_id, milestone_id, github_commit_id, confidence)
        SELECT r.owner_id,
               r.project_id,
               m.id,
               r.github_commit_id,
               r.confidence
          FROM _worktrace_evidence_reclassify r
          JOIN project_milestones m
            ON m.owner_id = r.owner_id
           AND m.project_id = r.project_id
           AND m.milestone_key = r.milestone_key
        ON CONFLICT (owner_id, milestone_id, github_commit_id) DO NOTHING;

        PERFORM worktrace_refresh_commit_derived_wbs(project_row.owner_id, project_row.project_id);
    END LOOP;
END;
$$;
