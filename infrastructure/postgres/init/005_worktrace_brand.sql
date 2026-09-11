UPDATE projects
SET title = 'worktrace', updated_at = now()
WHERE lower(title) = 'work-support';

UPDATE repository_sources
SET full_name = 'Leegiyeon/worktrace', updated_at = now()
WHERE lower(full_name) = 'leegiyeon/work-support';
