# work-support

`work-support`는 개인 업무 기록을 프로젝트 단위로 관리하고,
진행률·잔여 업무·주간 리포트·경력 자산화까지 연결하기 위한
업무 자동화 플랫폼입니다.

현재 저장소는 **개인용 1차 서비스(v0.1)** 단계입니다. MacBook에서
프론트엔드·백엔드·PostgreSQL을 실행하고, 매일 업무를 기록한 뒤
프로젝트 진행·성과 근거·경력 문장·리포트까지 연결할 수 있습니다.

## 현재 구현된 범위

- 프로젝트 생성/조회/수정/삭제 API
- 프로젝트 목록/생성/상세 화면
- 프로젝트별 업무 생성/조회/수정/삭제 API와 화면
- 업무 상태: `planned`, `in_progress`, `done`, `on_hold`
- 업무 우선순위: `low`, `medium`, `high`
- 업무 마감일 저장/수정
- 완료 업무 기준 프로젝트 진행률과 잔여 업무 수 표시
- 대시보드에서 진행 중 프로젝트와 잔여 업무 표시
- 문서 메타데이터/추출 항목/업무 로그 기반 주간 리포트 생성 API와 화면
- 대시보드 빠른 업무 기록과 지연·진행·고우선순위 실행 대기열
- 업무 로그 생성/조회/수정/삭제와 OpenAI 기반 검토용 초안 생성
- 프로젝트 성과 생성/조회/수정/삭제와 근거 업무 로그 연결
- 근거 기반 경력 자산 생성, 사용자 편집·저장, Markdown 복사
- 로컬 개발용 샘플 seed 데이터 생성 스크립트
- PostgreSQL + pgvector Docker Compose 구성
- `/health` 헬스체크 API

아직 파일 업로드, AI 문서 분석, RAG, 로그인, 배포/백업 자동화는 구현하지 않았습니다.

## 기술 스택

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Python
- Database: PostgreSQL + pgvector
- File Storage: 로컬 저장소 우선(`storage/uploads`), 추후 S3/Supabase Storage 확장 가능
- Container: Docker Compose
- AI: OpenAI Responses API 기반 업무 로그 초안, API key가 없으면 나머지 기능은 계속 사용 가능

## 디렉토리 구조

```text
work-support/
├─ frontend/                    # Next.js 앱과 프론트 API proxy
├─ backend/                     # FastAPI 앱, DB 초기화 스크립트, 테스트
├─ infrastructure/postgres/init/ # PostgreSQL 초기화 SQL, pgvector extension
├─ storage/uploads/             # 로컬 업로드 저장소 placeholder
├─ docs/                        # 설계/운영 문서 확장 위치
├─ DESIGN.md                    # 제품 정보 구조와 UI/UX 구현 계약
├─ docker-compose.yml
├─ .env.example                 # Docker Compose용 루트 환경변수 예시
├─ AGENTS.md
└─ README.md
```

## 빠른 시작: Docker Compose로 전체 실행

MacBook에서 가장 단순한 실행 방법입니다. Docker Desktop이 실행 중이어야 합니다.

```bash
cp .env.example .env
# .env에서 POSTGRES_PASSWORD와 REPORT_ACCESS_TOKEN을 실제 로컬 값으로 채웁니다.
docker compose up -d --build
```

실행 후 접속 URL:

- Frontend: <http://localhost:3000>
- Backend API: <http://localhost:8000>
- Backend health check: <http://localhost:8000/health>
- Backend API docs: <http://localhost:8000/docs>
- Projects UI: <http://localhost:3000/projects>
- Weekly report UI: <http://localhost:3000/reports>
- PostgreSQL: `localhost:5432`

Docker Compose는 기본적으로 host port를 `127.0.0.1`에만
바인딩합니다. 개인 로컬 개발 외부로 노출하지 않는 전제입니다.
`docker-compose.yml`과 `.env.example`은 Compose project name을
`work-support`로 고정합니다. Docker Desktop에서는 `work-support`
프로젝트 아래 `db`, `backend`, `frontend` 컨테이너만 관리되도록
실행하세요.
프론트엔드 컨테이너는 `app/`, `public/`, 설정 파일만 bind mount하고
`.next`, `node_modules`, `next-env.d.ts` 같은 생성물은 컨테이너/볼륨
안에서만 다루도록 구성했습니다.

현재 상태 확인:

```bash
docker compose ps
docker ps --filter label=com.docker.compose.project=work-support
```

중지/재시작:

```bash
docker compose down
docker compose up -d --build
```

## DB만 Docker로 실행하고 앱은 로컬에서 실행

프론트/백엔드를 로컬 프로세스로 띄우며 개발할 때 사용합니다.

### 1. PostgreSQL 실행

```bash
cp .env.example .env
# .env에서 POSTGRES_PASSWORD를 실제 로컬 값으로 채웁니다.
docker compose up -d db
```

DB 상태 확인:

```bash
docker compose ps db
```

### 2. Backend 실행

Python 3.10 이상을 권장합니다.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# backend/.env에서 POSTGRES_PASSWORD를 루트 .env와 같은 값으로 채웁니다.
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend 확인:

```bash
curl http://localhost:8000/health
```

예상 응답:

```json
{"status":"ok"}
```

### 3. Frontend 실행

새 터미널에서 실행합니다.

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Frontend 확인:

- <http://localhost:3000>
- <http://localhost:3000/projects>
- <http://localhost:3000/reports>

프론트엔드의 `/api/*` 라우트는 `frontend/.env.local`의
`WORK_SUPPORT_BACKEND_URL=http://localhost:8000` 값을 사용해
백엔드와 통신합니다.

### Frontend UI polish conventions

프론트엔드 UI는 `frontend/app/globals.css`의 공통 토큰과 컴포넌트
클래스를 우선 사용합니다. Apple-inspired 방향성은 장식 추가가 아니라
업무 도구의 밀도와 일관성을 높이는 기준입니다.

- 색상, radius, shadow, control height는 `:root` 토큰을 재사용합니다.
- Dashboard, Projects, Reports는 `page-shell`, `dashboard-topbar`,
  `summary-grid`, `dashboard-grid`, `panel`, `data-table`, `dense-list`
  리듬을 공유합니다.
- 한국어 B2B 업무 화면의 실용성을 위해 카드 간격은 작게 유지하고,
  제목·배지·테이블·폼 컨트롤의 높이를 맞춥니다.
- UI polish는 frontend-only로 처리하며 backend API payload, proxy route,
  dependency 변경 없이 검증합니다.

## 환경변수 정리

### 루트 `.env`

루트 `.env.example`은 Docker Compose 실행용입니다.

```bash
cp .env.example .env
```

주요 값:

- `POSTGRES_DB`: `work_support` — 로컬 DB 이름
- `POSTGRES_USER`: `leegiyeon` — 로컬 DB 사용자
- `POSTGRES_PASSWORD`: 빈 placeholder — 루트 `.env`에만 실제 로컬 비밀번호 입력
- `POSTGRES_HOST`: `db` — Docker backend가 DB 컨테이너에 접속할 때 사용
- `BACKEND_PORT`: `8000` — host에 노출할 backend port
- `FRONTEND_PORT`: `3000` — host에 노출할 frontend port
- `NEXT_PUBLIC_API_BASE_URL`: `http://localhost:8000` — 브라우저 안내용
- `WORK_SUPPORT_BACKEND_URL`: `http://backend:8000` — Docker frontend용
- `DEFAULT_OWNER_ID`: `local-owner` — 개인 로컬 데이터 owner 기본값
- `REPORT_ACCESS_TOKEN`: 빈 placeholder — 루트 `.env`에만 실제 로컬 토큰 입력
- `REPORT_TIMEZONE`: `Asia/Seoul` — 리포트 기간 경계 해석 기준
- `NEXT_PUBLIC_WORK_SUPPORT_OWNER_ID`: `local-owner` — 과거 호환용 공개 owner
- `OPENAI_API_KEY` / `OPENAI_MODEL`: 빈 placeholder — 필요 시 루트 `.env`에만 입력

### Backend 로컬 `.env`

로컬 backend 프로세스는 `backend/.env.example`을 복사합니다.

```bash
cd backend
cp .env.example .env
```

이 파일의 DB 설정은 `POSTGRES_HOST=localhost`, `POSTGRES_USER=leegiyeon`을
사용합니다. 실제 DB 비밀번호는 `backend/.env`의 `POSTGRES_PASSWORD`에만
입력하고 커밋하지 않습니다. `DATABASE_URL`을 직접 쓰는 경우에도 host는
`localhost` 또는 `127.0.0.1`이어야 합니다.
로컬 직접 실행은 `127.0.0.1` 바인딩을 기본으로 사용합니다.
`0.0.0.0`은 Docker 컨테이너 내부 바인딩에서만 사용하세요.

### Frontend 로컬 `.env.local`

로컬 frontend 프로세스는 `frontend/.env.example`을 복사합니다.

```bash
cd frontend
cp .env.example .env.local
```

이 파일의 `WORK_SUPPORT_BACKEND_URL`은 `http://localhost:8000`을
바라봅니다. `WORK_SUPPORT_OWNER_ID`와 `WORK_SUPPORT_REPORT_TOKEN`은
프론트 서버 라우트가 백엔드 호출 시 주입하는 server-only 값입니다.

## API 오류 형식

FastAPI/Pydantic 요청 검증 실패는 기본 422 응답을 유지합니다.
애플리케이션/인증/설정/DB 오류는 다음처럼 `detail` 안에
`{code, message}` 객체를 담습니다.

```json
{
  "detail": {
    "code": "DATABASE_UNAVAILABLE",
    "message": "Database is unavailable or the report schema is not initialized."
  }
}
```

프론트엔드는 문자열 `detail`과 `{code, message}` 객체를 모두
사용자 메시지로 변환합니다.

## DB 초기화 / migration 방법

현재 별도 migration 도구는 없고, canonical SQL source는
`infrastructure/postgres/init/002_work_support_schema.sql`입니다.

### 새 DB 첫 실행

`docker compose up -d db` 또는 `docker compose up --build`로
PostgreSQL 컨테이너를 처음 만들면 `infrastructure/postgres/init/`의
SQL이 자동 실행됩니다.

### 기존 DB에 스키마 재적용

스키마 SQL은 대부분 `CREATE ... IF NOT EXISTS`와
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 기반이므로 로컬 개발 중
재적용할 수 있습니다.

로컬 backend 환경:

```bash
cd backend
source .venv/bin/activate
python scripts/init_db.py
```

Docker DB 컨테이너에 직접 적용:

```bash
cat infrastructure/postgres/init/002_work_support_schema.sql \
  | docker compose exec -T db psql -U leegiyeon -d work_support
```

### 로컬 DB를 완전히 초기화해야 할 때

아래 명령은 로컬 DB volume을 삭제합니다. 저장된 로컬 데이터가 사라집니다.

```bash
docker compose down -v
docker compose up --build
```

## 로컬 PostgreSQL 백업 / 복원

백업과 복원은 Docker Compose의 `db` 서비스만 대상으로 합니다. 스크립트는
컨테이너 안의 `POSTGRES_DB` / `POSTGRES_USER` 환경변수를 사용하므로 DB
비밀번호를 명령 출력이나 인자로 노출하지 않습니다.

### 백업 생성

```bash
docker compose up -d db
scripts/backup_local.sh
```

백업 파일은 기본적으로 `backups/postgres/work_support_YYYYMMDDTHHMMSSZ.dump`
형식으로 생성됩니다. `backups/`는 git 추적에서 제외되며, 디렉토리는 `700`,
백업 파일은 `600` 권한으로 저장됩니다.

다른 위치에 저장해야 할 때만 `BACKUP_DIR`을 지정합니다.

```bash
BACKUP_DIR=/path/to/private/backups scripts/backup_local.sh
```

### 백업 복원

복원은 현재 로컬 DB 객체를 백업 내용으로 교체할 수 있으므로 명시적인
확인 플래그가 필요합니다. 파일이 없거나 읽을 수 없거나 비어 있으면 복원을
시작하지 않습니다.

```bash
scripts/restore_local.sh --confirm backups/postgres/work_support_YYYYMMDDTHHMMSSZ.dump
```

현재 데이터를 보존해야 한다면 복원 전에 새 백업을 먼저 만듭니다.

## 로컬 테스트용 샘플 데이터 생성

처음 실행 후 실제 사용 흐름을 빠르게 확인하려면 로컬 seed 스크립트를 실행합니다.
이 스크립트는 **개발/로컬 환경 전용**이며, 기존 `[샘플]` 프로젝트 데이터를
삭제한 뒤 다시 생성합니다. 실제 운영 데이터와 혼동되지 않도록 모든 샘플
프로젝트/업무/로그/성과 제목에는 `[샘플]` 표시가 붙습니다.

### Docker Compose backend 컨테이너에서 실행

```bash
docker compose up -d db backend
docker compose exec backend python scripts/seed_local.py
```

### 로컬 backend 가상환경에서 실행

```bash
cd backend
source .venv/bin/activate
python scripts/seed_local.py
```

생성되는 데이터:

- 샘플 프로젝트 2개
- 프로젝트별 업무 총 7개
- 업무 로그 6개
- 개선 성과 2개
- 경력 자산 예시 2개(`career_assets`, `generation_method=seed_template`)

실행 후 <http://localhost:3000> 또는 <http://localhost:3000/projects>에서
`[샘플]` 프로젝트와 잔여 업무/진척도를 확인할 수 있습니다.

### 대화 기반 사용자 프로젝트 seed 생성

기존 데이터는 삭제하지 않고, 중복 실행해도 같은 데이터가 반복 생성되지 않습니다.
생성 데이터는 `[user_project_seed]` 제목과 `generation_method=user_project_seed`로 구분됩니다.

```bash
# Docker Compose backend 컨테이너
docker compose up -d db backend
docker compose exec backend python scripts/seed_local.py --user-projects

# 로컬 backend 가상환경
cd backend
source .venv/bin/activate
python scripts/seed_local.py --user-projects
```

생성되는 데이터:

- `[user_project_seed] work-support`
- `[user_project_seed] OCC AI 민원 플랫폼`
- `[user_project_seed] E-manual RAG Chatbot`
- 프로젝트별 업무 3~5개, 업무 로그 2~3개, 성과 후보 1~2개, 경력 자산 1개

수치 성과는 임의 생성하지 않습니다. 수치가 확정되지 않은 성과는
`metric_value=NULL`, `metric_unit=추정 입력 필요`, `resume_ready=false`로 저장됩니다.

옵션:

```bash
# 기존 [샘플] 데이터를 지우지 않고 추가 생성
python scripts/seed_local.py --no-reset

# owner id를 바꿔 생성
python scripts/seed_local.py --owner-id local-owner
```

`APP_ENV`가 `local`, `dev`, `development`, `test`가 아니면 기본적으로
실행을 막습니다. 비로컬 DB에 실수로 넣지 않기 위한 보호 장치입니다.
정말 필요한 경우에만 `--force`를 사용하세요.

## API 연결 확인

### Health check

```bash
curl http://localhost:8000/health
```

### Projects API

```bash
curl -H "X-Work-Support-Owner-Id: local-owner" \
  -H "X-Work-Support-Report-Token: dev-only-report-token" \
  http://localhost:8000/projects
```

프로젝트와 업무를 API로 직접 확인하려면 다음처럼 호출합니다.

```bash
PROJECT_ID=$(curl -sS -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -H "X-Work-Support-Owner-Id: local-owner" \
  -H "X-Work-Support-Report-Token: dev-only-report-token" \
  -d '{"title":"v0.1 실행 점검","status":"in_progress","description":"로컬 사용 흐름 확인"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://localhost:8000/projects/${PROJECT_ID}/tasks" \
  -H "Content-Type: application/json" \
  -H "X-Work-Support-Owner-Id: local-owner" \
  -H "X-Work-Support-Report-Token: dev-only-report-token" \
  -d '{"title":"첫 업무 등록","status":"planned","priority":"high","due_date":"2026-06-07"}'

curl -sS http://localhost:8000/projects/${PROJECT_ID} \
  -H "X-Work-Support-Owner-Id: local-owner" \
  -H "X-Work-Support-Report-Token: dev-only-report-token"
```

### Weekly report API

```bash
curl -X POST http://localhost:8000/reports/weekly \
  -H "Content-Type: application/json" \
  -H "X-Work-Support-Owner-Id: local-owner" \
  -H "X-Work-Support-Report-Token: dev-only-report-token" \
  -d '{"start_date":"2026-06-01","end_date":"2026-06-07"}'
```

### Frontend → Backend proxy 확인

프론트엔드 실행 후 브라우저에서 <http://localhost:3000/projects>를
열어 프로젝트 목록이 로딩되는지 확인합니다. 문제가 있으면 다음을
확인하세요.

- Docker 전체 실행: 루트 `.env`의 `WORK_SUPPORT_BACKEND_URL=http://backend:8000`
- 로컬 frontend 실행: `frontend/.env.local`의 `WORK_SUPPORT_BACKEND_URL=http://localhost:8000`
- Backend CORS origin: `FRONTEND_ORIGIN=http://localhost:3000`
- Backend health: <http://localhost:8000/health>

## 개발 검증 명령

```bash
# Backend tests
cd backend
source .venv/bin/activate
pytest -q
cd ..

# Frontend checks
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build

# Compose syntax/services
docker compose config --services
```

## 자주 겪는 문제

### `relation "project_tasks" does not exist`

DB volume이 오래되어 최신 SQL이 적용되지 않은 상태입니다. 다음 중 하나를 실행하세요.

```bash
# 데이터 유지, 스키마만 재적용
cat infrastructure/postgres/init/002_work_support_schema.sql \
  | docker compose exec -T db psql -U leegiyeon -d work_support

# 또는 로컬 DB 데이터 삭제 후 재생성
docker compose down -v
docker compose up --build
```

### 3000 또는 8000 포트 충돌

Docker Desktop에서 `work-support` 프로젝트 밖의 컨테이너나 로컬
`node`/`uvicorn` 프로세스가 같은 포트를 잡고 있으면 하나로 통일합니다.

```bash
# 3000 포트를 잡고 있는 로컬 프로세스 확인
lsof -nP -iTCP:3000 -sTCP:LISTEN

# work-support Compose 컨테이너만 다시 실행
docker compose down
docker compose up -d --build
docker compose ps
```

다른 로컬 프론트엔드를 동시에 띄워야 할 때만 루트 `.env`에서
`FRONTEND_PORT`를 바꾸고 Compose를 재실행합니다. 기본 운영은
`work-support` Compose 프로젝트 하나로 `db`, `backend`, `frontend`를
함께 관리하는 방식입니다.

### 프론트에서 API 오류가 표시됨

1. `curl http://localhost:8000/health`로 백엔드가 떠 있는지 확인합니다.
2. Docker 실행이면 루트 `.env`, 로컬 실행이면
   `frontend/.env.local`의 `WORK_SUPPORT_BACKEND_URL`을 확인합니다.
3. 리포트 API는 `WORK_SUPPORT_REPORT_TOKEN` /
   `REPORT_ACCESS_TOKEN` 값이 일치해야 합니다.

## 현재 아키텍처 tradeoff

이 저장소는 개인 로컬 MVP를 빠르게 실행하기 위한 구조입니다.
아래 항목은 의도된 단순화이며, 외부 노출 또는 다중 사용자 전환 전에
반드시 재설계합니다.

- **접근 가드**: Next.js 서버 라우트가 `WORK_SUPPORT_OWNER_ID`와
  `WORK_SUPPORT_REPORT_TOKEN`을 백엔드 헤더로 주입합니다. 이는
  loopback-only 개인 실행을 위한 임시 경계이며 로그인/권한 시스템이
  아닙니다.
- **상태값 계약**: 프로젝트/업무/리포트 상태값은 SQL check constraint,
  Pydantic schema, frontend type/label map에 명시적으로 반복되어 있습니다.
  MVP에서는 변경 지점을 눈에 보이게 두기 위한 선택이며, 상태값이
  늘어나기 전 공통 contract 또는 생성 방식으로 정리합니다.
- **스키마 관리**: 현재는 versioned migration 대신 canonical SQL source와
  재실행 가능한 초기화 스크립트를 사용합니다. 파괴적 변경이나 협업
  배포가 필요해지면 migration 도구를 도입합니다.

## 현재 v0.1 범위에서 하지 않은 것

- 문서 업로드·텍스트 추출·AI 문서 분석
- 문서 청크 검색·임베딩·근거 기반 Q&A
- 배포 작업
- 로그인/권한 체계 도입

## 보안 주의

- 실제 secret은 `.env` 또는 `.env.local`에만 저장하고 커밋하지 않습니다.
- `.env.example` 파일은 placeholder만 제공합니다. DB 비밀번호, report token,
  OpenAI key는 실제 `.env` / `.env.local`에만 입력합니다.
- 외부 네트워크에 노출하기 전에 DB 비밀번호, report token, CORS origin,
  인증 방식을 반드시 교체/강화해야 합니다.
- 업로드 원본 파일은 추후에도 public 경로에 직접 노출하지 않는 구조를 유지합니다.
