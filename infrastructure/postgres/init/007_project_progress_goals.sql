ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS objective TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS success_criteria TEXT NOT NULL DEFAULT '';

ALTER TABLE project_tasks
    ADD COLUMN IF NOT EXISTS counts_toward_progress BOOLEAN NOT NULL DEFAULT true;

UPDATE project_tasks
SET counts_toward_progress = false
WHERE source_provider = 'github'
  AND source_key LIKE 'commit:%';

UPDATE project_tasks
SET counts_toward_progress = false
WHERE source_provider = 'github'
  AND source_key LIKE 'pr:%';

UPDATE projects
SET objective = '관제 업무를 하나의 운영 플랫폼으로 통합하고 실제 운영자가 안정적으로 사용할 수 있는 서비스와 신뢰 가능한 AI 업무 지원 기능을 구축·운영한다.',
    success_criteria = '핵심 업무 전산화, 운영 대시보드 정합성, 외부 데이터 연동, AI Assistant 신뢰성, 운영 안정성, 배포·복구 체계를 모두 검증한다.'
WHERE lower(title) = 'oncc';

UPDATE projects
SET objective = '업무 매뉴얼을 검색하는 수준을 넘어 실제 업무 질문에 근거를 제시하며 신뢰성 있게 답변하는 RAG 기반 업무지원 서비스를 구축한다.',
    success_criteria = '문서 수집·정제, 임베딩, 검색 품질, 근거 기반 답변, citation, 평가 체계, 운영화를 검증한다.'
WHERE lower(title) IN ('emanual', 'e-manual');

UPDATE projects
SET objective = '매일 수행한 업무를 자동으로 증거화하고 이를 프로젝트 진행·성과·경력 자산으로 연결하는 개인 Work Intelligence 플랫폼을 구축한다.',
    success_criteria = '프로젝트/WBS 관리, Work Capture, GitHub Evidence, Outcome, Career AI, Work Memory, Project Insight, 운영 안정성을 검증한다.'
WHERE lower(title) = 'worktrace';
