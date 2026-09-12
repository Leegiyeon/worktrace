CREATE TABLE IF NOT EXISTS project_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    milestone_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    acceptance_criteria TEXT NOT NULL DEFAULT '',
    weight INTEGER NOT NULL CHECK (weight > 0 AND weight <= 100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, project_id, milestone_key)
);

CREATE INDEX IF NOT EXISTS idx_project_milestones_owner_project
    ON project_milestones (owner_id, project_id, sort_order, created_at);

ALTER TABLE project_tasks
    ADD COLUMN IF NOT EXISTS milestone_id UUID REFERENCES project_milestones(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_project_tasks_milestone_id
    ON project_tasks (milestone_id)
    WHERE milestone_id IS NOT NULL;

INSERT INTO project_milestones (owner_id, project_id, milestone_key, title, acceptance_criteria, weight, sort_order)
SELECT p.owner_id, p.id, seed.key, seed.title, seed.criteria, seed.weight, seed.sort_order
FROM projects p
CROSS JOIN (VALUES
    ('core-digitization', '핵심 업무 전산화', '민원·출동·일지 등 핵심 관제 업무가 서비스에서 정상 CRUD 및 조회 가능하다.', 25, 10),
    ('operations-dashboard', '운영 대시보드', '실시간·기간별 주요 운영 지표가 정의된 집계 기준과 일치하고 검증된다.', 15, 20),
    ('external-integration', '외부 데이터 연동', 'Vox 등 외부 데이터가 API·Webhook으로 중복 없이 안정적으로 동기화된다.', 15, 30),
    ('ai-assistant', 'AI Assistant 신뢰성', '기간·도메인·집계 기준을 보존하고 근거 없는 응답을 차단하는 회귀 검증을 통과한다.', 20, 40),
    ('operations-reliability', '운영 안정성', '인증·세션·rate limit·백업·모니터링·장애 대응 기준이 검증된다.', 15, 50),
    ('delivery-recovery', '배포·복구 체계', 'DEV→운영 배포와 신규 서버 이관·복구 절차가 재현 가능하게 검증된다.', 10, 60)
) AS seed(key, title, criteria, weight, sort_order)
WHERE lower(p.title) = 'oncc'
ON CONFLICT (owner_id, project_id, milestone_key) DO UPDATE
SET title = EXCLUDED.title,
    acceptance_criteria = EXCLUDED.acceptance_criteria,
    weight = EXCLUDED.weight,
    sort_order = EXCLUDED.sort_order,
    updated_at = now();

INSERT INTO project_milestones (owner_id, project_id, milestone_key, title, acceptance_criteria, weight, sort_order)
SELECT p.owner_id, p.id, seed.key, seed.title, seed.criteria, seed.weight, seed.sort_order
FROM projects p
CROSS JOIN (VALUES
    ('document-ingestion', '문서 수집·정제', '대상 문서를 안정적으로 수집·정제하고 동일 입력을 재처리할 수 있다.', 15, 10),
    ('embedding-index', 'Chunk·Embedding', '문서 구조와 의미를 보존하는 chunk가 embedding되어 검색 인덱스로 관리된다.', 15, 20),
    ('retrieval-quality', 'Retrieval 품질', '대표 평가 질문에서 필요한 근거가 정의된 Top-K 안에 안정적으로 포함된다.', 20, 30),
    ('grounded-answer', '근거 기반 답변', '제공된 문서 근거만 사용하고 확인할 수 없는 내용은 확인 불가로 응답한다.', 20, 40),
    ('citation', 'Citation', '답변에서 사용자가 원문 문서와 페이지 등 근거 위치를 확인할 수 있다.', 10, 50),
    ('evaluation', '평가 체계', '고정 평가셋으로 retrieval·answer 품질의 회귀를 반복 검증할 수 있다.', 10, 60),
    ('operations', '운영화', '재색인·로그·장애 대응과 실제 사용자 환경에서의 실행이 검증된다.', 10, 70)
) AS seed(key, title, criteria, weight, sort_order)
WHERE lower(p.title) IN ('emanual', 'e-manual')
ON CONFLICT (owner_id, project_id, milestone_key) DO UPDATE
SET title = EXCLUDED.title,
    acceptance_criteria = EXCLUDED.acceptance_criteria,
    weight = EXCLUDED.weight,
    sort_order = EXCLUDED.sort_order,
    updated_at = now();

INSERT INTO project_milestones (owner_id, project_id, milestone_key, title, acceptance_criteria, weight, sort_order)
SELECT p.owner_id, p.id, seed.key, seed.title, seed.criteria, seed.weight, seed.sort_order
FROM projects p
CROSS JOIN (VALUES
    ('project-wbs', '프로젝트·WBS 관리', '프로젝트 목표·성취 기준·마일스톤·WBS가 연결되고 진척률이 계획 업무만으로 산정된다.', 15, 10),
    ('work-capture', 'Work Capture', '업무 기록을 빠르게 입력하고 적절한 프로젝트와 WBS에 연결할 수 있다.', 15, 20),
    ('github-evidence', 'GitHub Evidence', 'commit·issue·PR을 중복 없이 증거로 축적하되 자동 완료 근거로 오용하지 않는다.', 15, 30),
    ('outcome', 'Outcome', '활동 근거에서 성과 후보를 만들고 사용자 확인 후 확정할 수 있다.', 15, 40),
    ('career-ai', 'Career AI', '실제 evidence를 근거로 resume·STAR·portfolio 문안을 생성하고 약한 근거는 초안으로 표시한다.', 15, 50),
    ('work-memory', 'Work Memory', '과거 업무를 의미 기반으로 검색하고 답변에 근거를 함께 제시한다.', 10, 60),
    ('project-insight', 'Project Insight', 'blocker·우선순위·최근 활동·다음 행동을 프로젝트 단위로 분석한다.', 5, 70),
    ('operations', '운영 안정성', 'HTTPS·인증·배포·백업·복구가 실제 운영 환경에서 검증된다.', 10, 80)
) AS seed(key, title, criteria, weight, sort_order)
WHERE lower(p.title) = 'worktrace'
ON CONFLICT (owner_id, project_id, milestone_key) DO UPDATE
SET title = EXCLUDED.title,
    acceptance_criteria = EXCLUDED.acceptance_criteria,
    weight = EXCLUDED.weight,
    sort_order = EXCLUDED.sort_order,
    updated_at = now();
