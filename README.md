# worktrace

`worktrace`는 개인 업무 기록을 프로젝트 단위로 관리하고,
진행률·잔여 업무·주간 리포트·경력 자산화까지 연결하기 위한
업무 자동화 플랫폼입니다.

현재 저장소는 **개인용 1차 서비스(v0.1)** 단계입니다. 로컬 개발과 Oracle Cloud
단일 사용자 배포를 지원하며 GitHub 근거 수집, WBS·진척 관리, 업무 기록,
AI 검토, 경력 자료 생성까지 연결합니다. 저장소 이름은 `Leegiyeon/worktrace`,
운영 대상 도메인은 `worktrace.cloud`입니다.

이 문서는 2026-09-18 기준 저장소의 구현·설정을 설명합니다. 배포 성공 여부,
운영 DB 데이터, DNS·인증서·웹훅의 현재 상태는 별도 운영 점검이 필요합니다.
UI 구조는 [DESIGN.md](DESIGN.md), 공통 시각 규칙은
[디자인 시스템](docs/DESIGN_SYSTEM.md)을 참조합니다.

실사용을 위한 제품 방향·데이터 기준·우선순위·수용 기준은
[요구사항 재정의](docs/PRODUCT_REQUIREMENTS.md)에 정리했습니다.
이 문서는 앞으로의 제안 명세이며 아래 구현 현황과 구분합니다.

## 현재 구현된 범위

- 프로젝트 생성/조회/수정/삭제 API
- 프로젝트 목록/생성/상세 화면
- 프로젝트별 업무 생성/조회/수정/삭제 API와 화면
- 업무 상태: `planned`, `in_progress`, `done`, `on_hold`
- 업무 우선순위: `low`, `medium`, `high`
- 업무 마감일 저장/수정
- 진척 산정 대상 WBS와 마일스톤 가중치 기준 프로젝트 진행률·잔여 업무 표시
- 대시보드에서 진행 중 프로젝트와 잔여 업무 표시
- 문서 메타데이터/추출 항목/업무 로그 기반 주간 리포트 생성 API와 화면
- 저장된 업무·프로젝트 기록 기반 일간/주간/월간 리포트와 성과 후보 표시
- 대시보드 빠른 업무 기록과 지연·진행·고우선순위 실행 대기열
- GitHub 기준 브랜치 push webhook 수집, 프로젝트별 커밋 근거 조회, WBS/이슈 관리
- GitHub 이력·Issue·PR 동기화, 웹훅 상태·재처리, 원본 검토와 WBS 채택·연결
- 프로젝트 목표·성취 기준·마일스톤 관리, 검증센터의 AI 검토 이력 저장과 재검토 판정
- 인사이트의 Project Analyst: 목표·WBS·마일스톤·최근 커밋 기반 다음 행동과 확인 사항 제안
- 프로젝트별 단일 커밋 네트워크: 실제 부모 SHA 연결, 브랜치별 색상, 현재 HEAD 이름 표시
- 업무 로그 생성/조회/수정/삭제와 OpenAI 기반 검토용 초안 생성
- 프로젝트 성과 후보/검토 중/확정 목록, 근거 로그 검색·체크 선택과 내용 확인, 기존 문서 연결 보존
- 생성일 최신 경력 자산 우선 표시, 이전 버전 선택, 사용자 편집·저장과 현재 초안 Markdown 복사
- 로컬 개발용 샘플 seed 데이터 생성 스크립트
- PostgreSQL + pgvector Docker Compose 구성
- `/health/live`, `/health/ready` 생존·DB 준비 상태 API
- GitHub Actions 검증·Oracle SSH 배포, 단일 사용자 로그인, HTTPS 운영 Compose
- 체크섬 기반 SQL migration runner와 로컬/암호화 예약 백업 스크립트

파일 업로드·AI 문서 분석·RAG·다중 사용자 인증과 원격 백업 자동 복제는
아직 구현하지 않았습니다. 배포 코드가 있는 것과 운영 복구 절차가 검증된 것은 구분합니다.

## 실제 사용 흐름과 진척 기준

1. 프로젝트에 저장소를 연결하고 목표·성취 기준·마일스톤을 확인합니다. 최초 이력은 동기화 스크립트로 가져옵니다.
2. 저장소에 설정한 기준 브랜치(main 기본)의 push 웹훅으로 커밋 근거를 축적합니다. 일별 업무 로그는 최초 생성 시점의 요약이며 기존 내용은 덮어쓰지 않습니다. Issue·PR 원본은 별도 동기화 스크립트가 수집하며 push 웹훅이 갱신하지 않습니다.
3. 프로젝트의 `GitHub 근거`에서 수집된 Issue·PR을 검토하고 예정 업무로 채택하거나 기존 WBS에 연결합니다. 제외한 원본은 삭제하지 않으며 검토 대기로 복원할 수 있습니다. WBS에서는 마일스톤 연결과 진척 산정 포함 여부를 관리합니다. 커밋 수 자체를 완료 업무 수로 취급하지 않습니다.
4. 완료 검토(`/verifications`, 기존 검증센터)에서 프로젝트를 선택해 성취 기준·남은 WBS·저장된 확인 상태와 근거를 확인합니다. AI 검토는 필요할 때 명시적으로 실행하며 완료 확정은 사용자 동작으로 남습니다. 이 화면은 테스트 실행기나 서비스 가동 상태 감시 기능이 아닙니다.
5. 업무 로그·성과를 검토하고 경력 자료/주간 리포트를 생성합니다. AI 문장은 저장된 근거에 한정해 검토하고 확인되지 않은 수치를 성과로 확정하지 않습니다.

성과 후보는 최대 6건의 화면 제안이며 검토 저장 전에는 DB에 추가되지 않습니다.
검토 중 저장과 이력서 반영 확정은 기존 `resume_ready` 값으로 구분합니다.
화면에서 확정하려면 근거 연결과 사용자 확인이 필요하며, 내용이나 근거를 바꾸면 다시 확인합니다.
경력 자산의 최신 기준은 수정일이 아닌 생성일입니다. 이전 버전을 수정해도 최신 생성 결과를 대체하지 않습니다.
성과는 같은 프로젝트 탭/목록 이동, 경력 자산은 패널 내 버전 전환·생성 범위에서 입력을 보호합니다.
이 두 화면의 새로고침·전역 경로 이동 초안 복원은 지원하지 않습니다.

진척률의 기준은 `backend/app/services/projects.py`의 집계입니다.

자동 리포트의 `현재 WBS 진척`도 동일한 집계를 사용합니다. 프로젝트 상태·문서 수·업무 로그 수에 임의 점수를 더하지 않습니다. 선택 기간의 자료 또는 현재 잔여 WBS가 있는 프로젝트의 **리포트 생성 시점 진척**이며 과거 종료일의 진척 스냅샷이 아닙니다. API와 Markdown에 기준 시각·완료/전체 수·산정 방식·자동 구성 여부·승인 상태와 버전을 포함합니다. `계획 미승인`, `계획 재승인 필요`, `기준 미확인`과 승인한 업무의 실제 `0%`를 구분합니다. `suggested_progress_percent`는 호환용 nullable 별칭이며 추정값이 아닙니다.

기간별 리포트의 조회 기준:
- `activity.transitions`: `REPORT_TIMEZONE`의 `[시작일 00:00, 종료 다음 날 00:00)`에 기록된 실제 상태 전이입니다. 재개 전 완료 이력도 남으며 업무명·현재 상태는 조회 시점 값입니다. 초기 등록·시스템 기록도 출처를 구분하고, 과거 합성 검증 WBS는 제외합니다. 완료일 미확인 자료의 과거 실적은 생성하지 않습니다.
- `activity.issues`: 선택 기간의 `work_logs.log_date`에 기록된 막힘입니다. 현재 미해결 이슈 수나 해결 이력이 아닙니다.
- `activity.outcomes`: 해당 기간에 수정된 `resume_ready=true` 성과입니다. 수정일은 달성일·최초 확인일이 아니며 수치는 저장된 사용자 입력 그대로 사용합니다. 근거 ID는 같은 소유자·프로젝트에서 현재 조회 가능한 자료만 포함합니다.
- `activity.current_tasks`: 전체 프로젝트의 조회 시점 잔여 산정 WBS입니다. 미승인·재승인 업무도 해당 상태를 표시하며 승인된 실적으로 간주하지 않습니다. 기존 `remaining_tasks`·`delayed_tasks`는 기간 내 **문서 추출 항목**인 호환 필드로 구분해서 유지합니다.
- `/reports/automatic`은 모든 원본과 현재 집계를 하나의 읽기 전용 repeatable-read 트랜잭션에서 조회합니다. `activity`에 조회 시각·시간대·기간 경계·스키마 버전·SHA-256 내용 해시가 반환됩니다. 동일 내용은 같은 해시를 유지하고 기록 변경 시 달라지며 조회 시각 자체는 해시에서 제외합니다.
- 이 결과는 응답에 담긴 조회 스냅샷이지 영구 저장한 리포트 버전이나 과거 상태 복원 기능이 아닙니다. 삭제된 원본·기간 밖 근거 전문을 별도로 보존하지 않으며 AI 호출 없이 생성합니다. 기간 변경·재생성 실패 시 이전 결과를 현재 결과로 표시하지 않습니다.

- `counts_toward_progress=true`인 WBS만 완료·전체·잔여 업무 수에 포함합니다.
- `019`부터 프로젝트 개요에서 산정 범위와 계산 방식을 명시적으로 승인합니다. 기본 방식은 완료 WBS/산정 WBS 비율이며, 마일스톤 연결 여부로 자동 전환하지 않습니다.
- 마일스톤 가중 방식을 선택하면 모든 산정 업무가 마일스톤에 배정되고, 양수 가중치 마일스톤마다 산정 업무가 있으며 가중치 합이 100이어야 합니다. 각 마일스톤의 실제 비율을 가중 합산한 뒤 마지막에 한 번 반올림합니다.
- 승인 전에는 `계획 미승인`, 승인한 범위와 현재 범위가 다르면 `계획 재승인 필요`이며 `progress_percent=null`입니다. 구버전 응답의 승인 정보가 없으면 `기준 미확인`으로 처리합니다. 미승인·미산정을 0%로 대체하지 않습니다. 실제 0%는 승인한 업무가 아직 하나도 완료되지 않은 경우입니다.
- 기존 자동 구성(`derived-github`) 업무를 포함하려면 승인 시 별도 확인이 필요합니다. 출처 자체는 그대로 보존하며 `derived_task_count`로 제공합니다. 과거 합성 `milestone-validation:*` 업무는 진척 분모/분자에서 제외하지만 원본 행을 삭제하거나 상태를 변경하지 않습니다. 그 외 산정 제외 업무에는 계획 승인 시 사유가 필요합니다.
- 대시보드·목록의 평균은 현재 승인된 프로젝트만 사용합니다. 사용자가 확인해 승인한 자동 구성 업무는 평균에 포함될 수 있으며 자동 생성 사실은 계속 표시합니다. 마일스톤 개별 비율은 등록 업무 현황으로, 프로젝트 승인 완료율과 구분합니다.
- 업무 완료/재개는 승인 범위를 바꾸지 않고 현재 진척에 반영됩니다. 업무 추가/삭제·제목/설명·산정 포함·마일스톤 배정·가중치 변경은 재승인 대상입니다. 단순 상태 전환·기한/우선순위 변경·GitHub 원본 수집은 승인 계획에 자동 편입되지 않습니다.
- `GET/POST /projects/{project_id}/plan`은 현재 범위, 선택 정책, 승인 버전과 최근 20건의 이력을 제공합니다. 승인은 사유·당시 범위 스냅샷·변경 주체·시각을 저장하며 버전/문맥 충돌과 동일 요청 재전송을 검사합니다. 이전 승인 이력은 수정할 수 없고 프로젝트 삭제 시 함께 삭제됩니다. 최초 배포가 기존 프로젝트를 자동 승인하지 않습니다.
- 프로젝트 `status=done`은 사용자가 정한 개발 종료 상태이며 WBS 완료율·성취 기준 확인과 별개입니다. 운영 중인 완료 프로젝트도 표현할 수 있고, GitHub 동기화는 기존 프로젝트 상태를 다시 진행 중으로 덮어쓰지 않습니다.
- `016`부터 개발 단계와 서비스 상태(`unknown / not_released / operating / retired`)를 별도로 저장합니다. 프로젝트 개요의 `개발·운영 상태`에서 사유와 함께 확인하며, 미완료 WBS가 있는 개발 종료에는 처리 사유가 필요합니다. WBS 상태·비율은 변경하지 않습니다. 기존 프로젝트는 운영 미확인으로 시작하며 과거 실제 종료일을 현재 날짜로 채우지 않습니다.
- 상태 변경은 `POST /projects/{project_id}/lifecycle`로만 처리합니다. 버전 충돌과 동일 요청 재전송을 검사하며, `GET`은 상태 및 최근 확인 20건을 반환합니다. 개발 재개는 현재 종료일을 비우지만 과거 확인 이력은 보존합니다. 일반 프로젝트 수정으로 개발 단계를 우회 변경하거나 생성 시 바로 완료 처리할 수 없습니다.
- `017`부터 업무 등록·상태 전환을 완료 처리 시각(`completed_at`)·버전·이전/다음 상태·변경 주체·선택 사유와 함께 같은 트랜잭션에 기록합니다. 메모 수정이나 동일 상태 저장은 완료일을 갱신하지 않습니다. 재개하면 현재 완료일은 비우고 이력은 보존합니다. 기존 완료 업무의 실제 완료일은 추정하지 않아 미확인으로 남습니다.
- WBS 수정 양식의 `상태 변경 이력`은 해당 소유자 업무의 최근 50건과 전체 건수를 조회합니다. 상태 PATCH에는 조회한 `expected_status_version`이 필요하며, 충돌은 409입니다. 저장 응답을 확인하지 못하면 초안을 보존하고 최신 상태 확인 후 재저장합니다. 사유 없는 변경은 `사유 미기록`이며 시스템 변경의 주체를 사용자로 추정하지 않습니다. 업무·프로젝트 삭제 시 연결 이력도 삭제됩니다.
- 대시보드의 `이번 주 완료 처리한 업무`는 한국 시간 월요일 00시부터 현재까지 기록된 완료 시각이 있고 현재 완료 상태인 업무입니다. 완료일 미확인·자동 구성(`derived-github`)·출처 필드가 없는 구버전 응답은 제외합니다. 과거 실제 작업일이나 모든 완료 전환 건수를 의미하지 않습니다. 상세의 `조회된 커밋 근거`는 조회 응답 건수이며 전체 저장 건수는 GitHub 수집 상태의 `저장 커밋`과 구분합니다.
- AI가 반환하는 confidence는 측정된 정확도가 아니므로 화면에 신뢰도 백분율로 표시하지 않습니다. 경력 자산 생성에는 확정 성과만 사용하고, 자동 구성 WBS는 실제 완료 실적에서 제외하며 AI 입력에 그 출처를 전달합니다. 기존 저장된 경력 자료는 자동 재작성하지 않습니다.
- `014` 이후 GitHub 동기화는 Issue·PR 원본을 `github_items`에 저장하고 WBS를 생성·수정하지 않습니다. 이전에 생성된 WBS의 상태·산정 여부는 보존합니다. 외부 closed 상태를 로컬 done으로 변환하지 않으며 PR 종료를 병합으로 간주하지 않습니다.
- `015`의 원본 검토는 `pending / adopted / ignored`와 판단 이력을 보존합니다. 명시적으로 채택한 신규 WBS는 `planned`, `source_provider=github-adopted`이며 진척 포함 여부를 선택합니다. 기존 업무 연결은 상태·산정 여부를 변경하지 않습니다. 이것은 전체 WBS 승인 계획·완료 확인 모델을 대체하지 않습니다.
- `014`는 기존 자동 WBS를 삭제하거나 비율을 소급 수정하지 않고, 새 근거로 자동 WBS를 생성·덮어쓰기·삭제하던 트리거를 중단합니다. 기존 항목의 재분류는 별도 사용자 검토가 필요합니다.
- `018`부터 완료 검토의 `수동 완료 확인`에서 사유와 Evidence 메모를 입력해 확인합니다. AI 키·AI 판단·기존 자동 검증 WBS 없이 사용합니다. 성취 기준이 비어 있거나 산정 대상의 실제 업무가 미완료면 서버가 차단합니다. 메모는 사용자의 확인 진술이며 자동 테스트 성공을 의미하지 않습니다.
- 확인/계획 재전환은 주체·시각·버전·당시 성취 기준/WBS/연결 커밋 스냅샷과 함께 별도 이력에 저장합니다. 이후 문맥이 바뀐 완료 확인은 `재확인 필요`로 표시합니다. 최근 20건을 조회하며 부모 마일스톤·프로젝트 삭제 시 이력도 삭제됩니다.
- `PATCH /projects/{project_id}/milestones/{milestone_id}/validation`은 `status`, `reason`, `evidence_note`, `expected_version`, `expected_context_fingerprint`, `request_id`가 필요합니다. 완료에는 비어 있지 않은 메모가 필요합니다. 충돌은 409이며 같은 요청 ID/본문의 재전송은 이력을 중복 생성하지 않습니다. 응답 유실 시 입력을 잠그고 같은 요청 재시도 또는 명시적인 근거 재조회를 제공합니다.
- 완료 확인은 업무 상태·프로젝트 상태·진척률을 변경하지 않습니다. 과거 `milestone-validation:*` 자동 검증 WBS는 수정/삭제를 차단하고 확인 이력으로 자동 승격하지 않습니다. 완료 검토와 프로젝트 집계 모두 이 합성 업무를 제외합니다. 산정 제외 업무가 있는 마일스톤은 사유를 포함한 현재 프로젝트 계획의 승인이 필요하며, 산정 체크 해제만으로 완료 조건을 우회할 수 없습니다.
- AI 검토는 DB에 저장되어 재진입 시 복원됩니다. WBS·근거·성취 기준이 바뀌면 이전 검토는 오래된 판단으로 표시합니다. AI 결과는 수동 완료 확인의 필수 조건이 아닙니다.
- 프로젝트 전체 AI 검토는 기본적으로 최신 검토와 이미 검증된 항목을 건너뜁니다. 강제 재검토도 이미 검증된 항목을 자동 변경하지 않습니다.
- WBS 추가/수정에서 마일스톤과 `진척 산정에 포함`을 선택합니다. 개별 업무는 상태와 산정 여부로 표시하며 진행 중=50% 같은 임의 비율은 사용하지 않습니다.
- 목표 저장은 다른 프로젝트의 미저장 입력과 저장 중 추가 편집을 보존합니다. 내부 링크·모바일 메뉴 이동 전 확인하며, 프로젝트 전환과 앱의 뒤로/앞으로 이동에도 현재 탭 메모리의 초안을 유지합니다. 탭 닫기/새로고침은 경고 후 승인하면 초안이 사라집니다.
- 목표·검증센터의 조회 실패는 빈 데이터와 구분하고 개별 재시도를 제공합니다. 검토 조회 실패 중에는 일괄 AI 실행을 차단합니다.

화면별 구현 현황과 기존 개선 목록은 [UI 개선 현황](docs/UI_IMPROVEMENT_PLAN.md)을 참고하세요.
제품 전체의 후속 우선순위는 [요구사항 재정의](docs/PRODUCT_REQUIREMENTS.md)를 기준으로 합니다.

프로젝트 목록은 검색·상태·정렬을 먼저 제공하며 생성 폼은 `프로젝트 추가`로 엽니다.
WBS는 목록이 기본이고 추가·수정할 때만 같은 폼을 사용합니다. 양식 숨기기는 페이지 안의
초안을 유지합니다. 프로젝트 목록의 `q/status/sort`, 상세의 `tab/view/status/priority/issue/sort`는
URL에 보존되어 새로고침과 뒤로 이동 시 조회 조건이 복원됩니다. 입력 초안을 영구 저장하는 기능은 아닙니다.
모바일 헤더는 화면 선택 메뉴, 지표는 2열이며, 대시보드는 지연 업무를 하나의 이슈 목록에 통합합니다.

업무 로그는 최신순 타임라인을 먼저 표시하고 검색·유형 필터로 찾습니다. 추가/수정할 때만 폼을 열며
상세 입력에는 결정·협업자·다음 액션·블로커·소요 시간을 보존합니다. 숨김과 같은 프로젝트 안의 탭 전환은
초안을 유지합니다. 목표 화면은 프로젝트 선택 후 조회가 기본이며 `목표 편집`으로 입력을 엽니다.
목표 초안은 브라우저 저장소에 기록하지 않고, 로그아웃 성공 시 제거합니다. 새 탭·브라우저 재시작 복원은 지원하지 않습니다.

## 브랜치 네트워크 조회 범위

기준 브랜치 포함 최대 13개 브랜치와 브랜치별 최근 100개 커밋을 조회합니다.
브랜치 HEAD SHA를 고정해 이력과 ahead/behind를 비교하며, 같은 커밋은 하나의 노드로 표시합니다.
조회 범위 밖의 부모는 점선 경계로 남기고 분기·병합 선을 추정하지 않습니다.
Squash/rebase 병합은 Git 부모 관계에 원래 작업 브랜치의 병합 선을 남기지 않으므로 PR 병합 기록과 구분해야 합니다.
브랜치 삭제 후에도 커밋 이력에 남아 있는 실제 merge 부모 관계는 표시됩니다.
기본 요약 보기에서는 분기·병합·HEAD를 유지하고 직선 구간의 중간 커밋을 접습니다.
접힌 구간은 점선으로 표시하며, 전체 커밋 보기로 조회된 이력을 모두 확인할 수 있습니다.
프로젝트를 선택하면 해당 저장소의 그래프 하나만 표시합니다. 겹치지 않는 과거 병합 경로는 행을 재사용합니다.
요약 그래프는 가용 폭에 맞춰 노드 간격을 계산하고, 같은 HEAD의 브랜치명은 `대표 이름 + 개수`로 묶습니다. 이름을 선택하면 전체 브랜치 상태가 열립니다.
라벨은 실제 글자 폭을 측정해 배치하며 그래프 글자 자체를 축소하지 않습니다. 요약은 내용 높이를 유지하고, 전체 커밋 보기만 데스크톱 최대 176px·모바일 최대 160px의 스크롤 영역을 사용합니다. 커밋 선택 시 메시지·날짜·GitHub 링크가 표시됩니다.
브랜치별 상세 상태는 펼침 목록으로 제공됩니다.

### 데이터 출처와 갱신

- 프로젝트 연결 정보와 기준 브랜치 이름은 DB의 `repository_sources`에서 읽습니다.
- 그래프 자체는 DB의 `github_commits`가 아니라 요청 시 GitHub API의 브랜치 HEAD, 커밋 SHA, 부모 SHA, 메시지, committer 날짜를 읽어 구성합니다. 이 GET 요청은 DB에 커밋을 저장하거나 업무 이력을 동기화하지 않습니다.
- 프로젝트 최초 선택, 다른 프로젝트 선택 후 재진입, 페이지 재진입/새로고침, 그래프 새로고침 시 조회합니다. 자동 폴링은 없으며 요약/전체 보기 전환과 커밋 선택은 이미 받은 데이터만 사용합니다.
- 브라우저·Next proxy 요청은 `no-store`이며 이 경로에 서버 캐시는 없습니다. 표시되는 조회 시각은 브라우저에서 응답 수신을 완료한 시각이며 웹훅의 마지막 동기화 시각과 다릅니다.
- GitHub 브랜치 목록의 첫 100개 중 기준 브랜치를 우선하고 나머지는 이름순으로 골라 최대 13개를 표시합니다. 기준 브랜치가 첫 페이지에 없으면 별도 조회합니다. 최근 활동 순으로 브랜치를 고르는 방식은 아닙니다.
- 각 HEAD에서 도달 가능한 최근 커밋을 최대 100개 읽습니다. 커밋 조회에는 `since` 날짜 조건이 없으며 main 외 브랜치의 이력도 포함합니다. 같은 SHA는 합쳐서 표시합니다.
- x축은 부모가 자식보다 먼저 오도록 배치한 연결 순서이며 시간에 비례하는 축이 아닙니다. API의 최근 30일 `activity` 집계는 그래프 좌표에 사용하지 않습니다.
- ahead/behind는 기준 브랜치 HEAD SHA와 해당 HEAD SHA를 GitHub compare API로 비교한 결과입니다. 정상적으로 기준 브랜치가 포함되면 N개 브랜치 조회에 GitHub 요청 2N회, 기준 브랜치 별도 조회 시 1회가 추가됩니다.
- 웹훅의 기준 브랜치 push 처리와 별도 이력 수집 스크립트가 DB의 커밋 근거·업무 로그를 저장하는 경로이며 그래프 조회와는 별개입니다.

## 기술 스택

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Python
- Database: PostgreSQL + pgvector
- File Storage: 로컬 저장소 우선(`storage/uploads`), 추후 S3/Supabase Storage 확장 가능
- Container: Docker Compose
- AI: OpenAI Responses API 기반 업무 로그 초안·통합 경력 자료·마일스톤 검토·Project Analyst. API key가 없거나 생성이 실패하면 경력 자료는 근거 기반 템플릿으로 폴백하며, 다른 AI 기능은 설정/생성 오류를 표시합니다.

## 디렉토리 구조

```text
worktrace/
├─ frontend/                    # Next.js 앱과 프론트 API proxy
├─ backend/                     # FastAPI 앱, DB 초기화 스크립트, 테스트
├─ infrastructure/postgres/init/ # PostgreSQL 초기화 SQL, pgvector extension
├─ storage/uploads/             # 로컬 업로드 저장소 placeholder
├─ docs/                        # 공통 디자인 시스템
├─ scripts/                     # 배포, 백업·복구, 로그인 해시 생성
├─ .github/workflows/ci-cd.yml   # 검증 및 Oracle 배포
├─ DESIGN.md                    # 제품 정보 구조와 UI/UX 구현 계약
├─ docker-compose.yml
├─ docker-compose.prod.yml      # 운영 빌드·DB migration·Caddy HTTPS
├─ docker-compose.oracle.yml    # 기존 Nginx용 loopback 포트 override
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

로컬에서도 로그인 경계를 확인하려면 12자 이상의 비밀번호 해시와 세션
비밀값을 `.env`에 설정합니다. 두 값을 비워두면 로컬 개발에서만 인증을
우회하며, production 모드에서는 설정 누락 시 접근을 거부합니다.

```bash
node scripts/generate_password_hash.mjs
openssl rand -base64 48
```

각 출력값을 `WORKTRACE_PASSWORD_HASH`, `WORKTRACE_SESSION_SECRET`에
저장합니다. 원문 비밀번호는 환경변수나 저장소에 보관하지 않습니다.
Compose 환경 파일의 비밀번호 해시는 작은따옴표로 감싸 `$` 문자가 변수로
치환되지 않도록 합니다. 비밀번호를 생성 명령의 인자로 전달하지 않습니다.

## 운영 컨테이너 사전 검증

`docker-compose.prod.yml`은 개발용 source mount와 reload를 사용하지 않고,
Caddy만 host의 80/443 port에 공개합니다. frontend, backend, database는
Compose 내부 network에서만 통신합니다. `APP_DOMAIN`의 DNS가 서버를 가리키면
Caddy가 인증서를 자동 발급하고 HTTP 요청을 HTTPS로 전환합니다.

운영 환경 파일은 `.env.production.example`을 복사해 준비합니다. 현재 운영
Compose의 볼륨은 기존 데이터 보존을 위해 `external: true`이며 실제 이름은
`work-support_postgres_data`, `work-support_caddy_data`, `work-support_caddy_config`입니다.
기존 서버에서는 해당 볼륨과 DB 이름을 유지합니다. 새 서버에서는 백업 복원 계획과
볼륨 준비를 먼저 마쳐야 하며 아래 실행만으로 기존 데이터가 이관되지는 않습니다.
Nginx 방식은 DB 볼륨을, Caddy 방식은 세 볼륨을 준비한 뒤 구성을 검증합니다.

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

운영 필수값은 `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`DEFAULT_OWNER_ID`, `REPORT_ACCESS_TOKEN`, `FRONTEND_ORIGIN`, `APP_DOMAIN`,
`WORKTRACE_PASSWORD_HASH`, `WORKTRACE_SESSION_SECRET`, `GITHUB_WEBHOOK_SECRET`입니다.
비공개 저장소 조회에는 접근 권한이 있는 `GITHUB_SYNC_TOKEN`도 필요합니다.
`FRONTEND_ORIGIN`은 `https://APP_DOMAIN`과 동일한 실제 HTTPS 주소여야 하며
기본 owner/token은 거부됩니다. Oracle Cloud VCN security list 또는 NSG에는
80/TCP, 443/TCP, 443/UDP만 공개하고 PostgreSQL 5432와 backend 8000은 열지
않습니다. SSH 22는 관리 IP CIDR로 제한합니다.
backend는 기동 전에 `backend/scripts/migrate_db.py`를 실행합니다. 적용된 SQL
파일명과 SHA-256 체크섬은 `schema_migrations`에 기록하며, 이미 적용된 SQL이
수정되었거나 migration이 실패하면 API 서버를 시작하지 않습니다. 기존 SQL을
수정하지 말고 다음 번호의 새 SQL 파일을 추가해야 합니다.

컨테이너 생존 확인은 `/health/live`, 서비스 준비 확인은 DB에 `SELECT 1`을
수행하는 `/health/ready`를 사용합니다. backend Compose healthcheck는 readiness를
기준으로 하므로 DB 연결이 끊긴 상태를 정상으로 판정하지 않습니다.

아래 URL은 별도 `docker-compose.yml`을 사용하는 로컬 개발 환경 기준입니다.
운영 환경에서는 `https://APP_DOMAIN`만 외부에 공개됩니다.

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
`worktrace`로 고정합니다. Docker Desktop에서는 `worktrace`
프로젝트 아래 `db`, `backend`, `frontend` 컨테이너만 관리되도록
실행하세요.
프론트엔드 컨테이너는 `app/`, `public/`, 설정 파일만 bind mount하고
`.next`, `node_modules`, `next-env.d.ts` 같은 생성물은 컨테이너/볼륨
안에서만 다루도록 구성했습니다.

현재 상태 확인:

```bash
docker compose ps
docker ps --filter label=com.docker.compose.project=worktrace
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
# 아래 'DB 초기화 / migration 방법'의 로컬 Python runner로 먼저 스키마를 준비합니다.
# DB 컨테이너만 시작하면 앱 테이블은 아직 생성되지 않습니다.
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
`WORKTRACE_BACKEND_URL=http://localhost:8000` 값을 사용해
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

- `POSTGRES_DB`: `worktrace` — 신규 로컬 DB 이름. 기존 운영 DB의 `work_support` 이름은 데이터 이전 전까지 유지할 수 있습니다.
- `POSTGRES_USER`: `leegiyeon` — 로컬 DB 사용자
- `POSTGRES_PASSWORD`: 빈 placeholder — 루트 `.env`에만 실제 로컬 비밀번호 입력
- `POSTGRES_HOST`: `db` — Docker backend가 DB 컨테이너에 접속할 때 사용
- `BACKEND_PORT`: `8000` — host에 노출할 backend port
- `FRONTEND_PORT`: `3000` — host에 노출할 frontend port
- `NEXT_PUBLIC_API_BASE_URL`: `http://localhost:8000` — 브라우저 안내용
- `WORKTRACE_BACKEND_URL`: `http://backend:8000` — Docker frontend용
- `DEFAULT_OWNER_ID`: `local-owner` — 개인 로컬 데이터 owner 기본값
- `REPORT_ACCESS_TOKEN`: 빈 placeholder — 루트 `.env`에만 실제 로컬 토큰 입력
- `REPORT_TIMEZONE`: `Asia/Seoul` — 리포트 기간 경계 해석 기준
- `NEXT_PUBLIC_WORKTRACE_OWNER_ID`: `local-owner` — 과거 호환용 공개 owner
- `OPENAI_API_KEY` / `OPENAI_MODEL`: 빈 placeholder — 필요 시 루트 `.env`에만 입력
- `GITHUB_WEBHOOK_SECRET`: GitHub 저장소 webhook과 동일한 임의의 긴 비밀값
- `GITHUB_SYNC_TOKEN`: GitHub API 조회용 서버 전용 토큰. 비공개 저장소 접근에 필요하며 웹훅 서명 비밀값과 다릅니다.
- `WORKTRACE_GITHUB_REPOSITORIES`: 기본 3개 외에 동기화할 `owner/repository`의 쉼표 구분 목록. 기본 저장소를 대체하지 않습니다.

### GitHub 기준 브랜치 push 자동 수집

1. 프로젝트 상세의 `GitHub 저장소 연결`에서 GitHub repository ID와 `owner/repository`를 저장합니다.
2. GitHub 저장소의 Webhooks 설정에 `https://worktrace.cloud/webhooks/github`를 추가합니다. 다른 환경에서는 도메인을 해당 `APP_DOMAIN`으로 바꿉니다.
3. Content type은 `application/json`, 이벤트는 `Just the push event`, Secret은 `GITHUB_WEBHOOK_SECRET`과 같은 값으로 설정합니다.
4. 연결 설정의 기준 브랜치(main 기본)에 push하면 delivery와 커밋 근거가 저장되고 프로젝트 상세의 `최근 커밋 근거`에 표시됩니다. 다른 delivery에 포함된 동일 SHA도 중복 저장하지 않습니다.

커밋은 수행 활동의 근거로만 취급합니다. WBS 완료나 성과 확정은 자동으로 단정하지 않으며, 경력 자산 생성 시 커밋·WBS·업무 로그·확정 성과를 함께 분석합니다.

기존 Git 이력을 최초 1회 가져올 때는 `backend/scripts/import_git_history.py`에 프로젝트명, 로컬 Git 경로, GitHub 저장소명과 repository ID를 전달합니다. 이미 저장된 SHA는 다시 추가하지 않습니다.
이 도구는 기존 프로젝트에 커밋 근거만 가져오며 Issue·PR·날짜별 업무 로그를 만들지는 않습니다.

GitHub API로 전체 사용 데이터를 준비하는 경로는 `backend/scripts/sync_github_data.py`입니다.
기본 대상은 `Leegiyeon/oncc`, `RotemSRS/emanual`, `Leegiyeon/worktrace`입니다.
설정된 기준 브랜치의 커밋, 최초 일별 요약 로그, Issue·PR 원본을 수집합니다.
기존 프로젝트 제목·설명·역할·목표·마일스톤과 기준 브랜치는 변경하지 않습니다.
새 저장소는 repository ID로 연결하며 같은 제목의 수동 프로젝트에 임의 연결하지 않습니다.
신규 프로젝트는 `idea`, 역할 미입력으로 생성하고 실제 계획을 추측해 채우지 않습니다.
커밋과 마일스톤의 키워드 연결은 검증 완료 증거가 아닌 분류 후보입니다.
페이지당 100개, 최대 100페이지를 읽습니다. 상한까지 마지막 페이지가 꽉 차면 부분 성공으로 취급하지 않고 실패하여 해당 동기화 트랜잭션을 되돌립니다. 대규모 이력의 분할 수집·재개 기능은 아직 없습니다.

```bash
# 로컬 Compose, GitHub 토큰은 루트 .env에 설정한 뒤 backend 컨테이너에 반영
docker compose exec -T backend python scripts/sync_github_data.py
docker compose exec -T backend python scripts/report_progress_snapshot.py
```

실행 전 `014_github_source_preservation.sql`까지 적용되어 있어야 합니다.
재실행 시 GitHub 원본만 갱신하며 오래된 Issue·PR 응답은 최신 원본을 되돌리지 않습니다.
사용자 편집 여부를 판별할 과거 이력이 없으므로 기존 업무 로그는 모두 보존합니다.
일별 로그의 제목/건수/내용은 최초 수집 시점의 스냅샷으로, 하루의 최종 집계가 아닙니다.
최신 커밋은 근거 목록에서 확인하며 로그 자동 갱신은 편집 이력·버전 정책 구현 후 재검토합니다.
기존 WBS는 삭제하지 않습니다. `015_github_item_review.sql`까지 적용하면 프로젝트의 `GitHub 근거` 탭에서 신규 Issue·PR을 검토·채택할 수 있습니다.

### GitHub 원본 검토 기준

- `GET /projects/{project_id}/github-items`는 GitHub 실시간 호출이 아니라 DB에 수집된 원본을 조회합니다. 화면의 새로고침도 DB 재조회이며 GitHub 동기화를 실행하지 않습니다.
- `review_status=pending|adopted|ignored|all`, `limit`(기본 20, 최대 100), `offset`으로 페이지를 조회합니다. 표시 건수는 전체 프로젝트의 상태별 건수이며 목록은 해당 필터의 결과입니다. 원본 수정일·수집일을 함께 표시합니다.
- `POST /projects/{project_id}/github-items/{item_id}/decision`은 `create / link / ignore / restore`를 처리합니다. `expected_version`, `expected_source_updated_at`, UUID `request_id`가 필요합니다. 다른 프로젝트·소유자의 업무에는 연결할 수 없습니다.
- 동일 요청의 재전송은 업무를 중복 생성하지 않습니다. 같은 요청 ID의 다른 내용·대상, 오래된 원본이나 판단 버전은 409로 거절합니다. 화면은 충돌 시 원본 재확인을 요구하고 저장 결과 미확인 시 같은 요청을 재전송합니다.
- 원본 내용 또는 수정 시각이 달라지면 버전이 증가합니다. 같은 초에 수정된 원문도 충돌 검사에 포함하고, 판단 이후 변경 여부는 저장한 원문 SHA-256과 수정 시각을 비교합니다. 동일 원문 재수집만으로 버전을 올리지는 않습니다.
- 판단 시점의 원본·요청·이전/이후 연결·시각을 감사 이력에 보존합니다. 재수집은 판단 상태를 되돌리지 않습니다. 연결한 WBS가 삭제되면 원본은 채택 상태로 남고 연결 없음으로 표시되어 기존 업무에 다시 연결할 수 있습니다.
- 현재 한 원본은 한 WBS에 연결되며 여러 원본을 같은 WBS에 연결할 수 있습니다. 임의 재배정, 커밋·로그의 다대다 근거 편집, 승인 계획 버전은 후속 범위입니다.
- UI의 입력은 같은 프로젝트 내 탭 이동 중 유지되지만 페이지 재로드·프로젝트 이탈 후 복원되지는 않습니다. 서버의 요청 중복 방지는 유지됩니다.
`--cleanup-samples`는 `[샘플]`/`[user_project_seed]` 프로젝트를 삭제하는 명시적 옵션이며
일반 수동 동기화에는 넣지 않습니다. `--max-commit-tasks`는 호환용이며 더 이상 커밋 업무를 만들지 않습니다.
독립 Python 실행에서는 토큰/추가 저장소 값을 환경변수로 export해야 합니다.
이 스크립트의 GitHub 클라이언트는 `.env`가 아닌 프로세스 환경에서 토큰을 읽습니다.

웹훅 성공은 HTTP 200만으로 판단하지 않고 응답의 `status`, `reason`, `commits_stored`와
프로젝트의 수신 이력을 확인합니다. `ping`은 `unsupported_event`, 기준 브랜치 이외 push는
`non_default_ref`, 연결되지 않은 저장소는 `repository_not_linked`로 무시됩니다. 과거 `non_main_ref` 이력도 표시합니다.
서명 불일치는 403, 서버 비밀값 누락은 503입니다. 동일 delivery 재전송은 중복 처리되므로
저장소 연결을 수정한 뒤에는 서비스의 재처리 기능으로 저장된 delivery를 다시 처리합니다.

### 기존 Nginx 서버에 Oracle 배포

호스트 Nginx가 이미 80/443을 사용한다면 Caddy를 실행하지 않고 frontend와 GitHub webhook용 backend만 loopback 포트에 노출합니다.

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.oracle.yml \
  up -d --build db backend frontend
```

Nginx는 일반 요청을 `http://127.0.0.1:3200`으로 reverse proxy합니다. `/webhooks/github`는 frontend 인증을 거치지 않도록 `http://127.0.0.1:8200`으로 직접 전달합니다. 두 포트 모두 loopback에만 바인딩되므로 외부에서는 Nginx를 통해서만 접근할 수 있습니다.

### GitHub Actions CI/CD

`.github/workflows/ci-cd.yml`은 `main` 대상 pull request와 `main` push, 수동 실행에서
backend 테스트, frontend 테스트·타입 검사·lint·build, 운영 Compose 검증과 이미지 빌드를 수행합니다.
`main` 실행의 검증이 성공하면 GitHub `production` environment의 SSH secrets로 Oracle 서버를 배포합니다. PR에서는 배포하지 않습니다.

- Environment secrets: `ORACLE_HOST`, `ORACLE_USER`, `ORACLE_SSH_KEY`, `ORACLE_KNOWN_HOSTS`
- GitHub 연동 값 `GITHUB_SYNC_TOKEN`, `GITHUB_WEBHOOK_SECRET`은 서버 `.env.production`에서 관리합니다. 워크플로는 해당 값을 SSH 명령문으로 전달하지 않습니다.

DB·로그인·OpenAI 등 나머지 애플리케이션 설정은 서버의 `/home/ubuntu/worktrace/.env.production`에서 관리합니다.
`ORACLE_KNOWN_HOSTS`는 별도 신뢰 경로로 지문을 확인한 서버 키여야 합니다.
이전 워크플로 secrets에만 연동 값을 넣었다면 새 배포 전 서버 환경 파일 설정을 확인해야 합니다. 비밀값을 CI 로그나 커밋에 옮기지 않습니다.
키·토큰·환경 파일은 커밋하지 않습니다.

CI는 검증한 SHA와 같은 checkout의 배포 스크립트를 SSH 표준 입력으로 전달합니다.
서버에 남은 이전 스크립트를 먼저 실행하지 않으며 `bash scripts/deploy_oracle.sh <40자리 SHA>` 형식을 사용합니다.
스크립트는 해당 SHA를 detached checkout하고 HEAD를 대조합니다. 기존 앱을 내리기 전에 migration 이력·체크섬을 사전 검증합니다.
서버 checkout에 미커밋 소스가 있으면 중단하며 자동 초기화·삭제하지 않습니다. Git에서 제외된 서버 환경 파일은 유지합니다.
SQL은 체크섬 runner로만 적용하며 배포 중 GitHub 동기화·샘플 삭제를 실행하지 않습니다.
readiness·로그인 응답과 읽기 전용 진척 스냅샷으로 기동을 확인합니다.
중단 시간과 자동 롤백 부재는 남아 있습니다. 이력 없는 기존 DB는 의도적으로 배포를 중단하며 아래 baseline 점검 절차가 필요합니다.

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

이 파일의 `WORKTRACE_BACKEND_URL`은 `http://localhost:8000`을
바라봅니다. `WORKTRACE_OWNER_ID`와 `WORKTRACE_REPORT_TOKEN`은
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

canonical SQL source는 `infrastructure/postgres/init/*.sql` 전체이며 현재 `001`부터 `016`까지 있습니다.
`backend/scripts/migrate_db.py`가 파일명 순서대로 적용하고 advisory lock·트랜잭션·체크섬을 관리합니다.
`002_work_support_schema.sql`은 기본 스키마 한 부분일 뿐이며 파일명은 migration 식별자 호환을 위해 유지합니다.

### 새 DB 첫 실행

DB 컨테이너는 빈 데이터베이스만 준비합니다. 로컬·운영 Compose 모두 backend 기동 전에
체크섬 runner가 전체 SQL과 적용 이력을 하나의 트랜잭션으로 기록합니다.
DB 초기화 디렉터리에 앱 SQL을 다시 마운트하지 않습니다.

### 기존 DB에 새 migration 적용

먼저 백업을 확보합니다. 로컬·운영 backend 모두 기동 전에 runner를 실행합니다.
실행 중인 backend에서 명시적으로 적용할 때는 아래 명령을 사용합니다.
이미 적용한 SQL을 편집하지 말고 다음 번호의 migration을 추가합니다.

```bash
docker compose exec -T backend python scripts/migrate_db.py
```

앱을 로컬 Python으로 실행하는 경우 `backend/.env`의 DB 설정을 읽어 전체 migration을 적용합니다.

```bash
cd backend
source .venv/bin/activate
python - <<'PY'
from pathlib import Path
from app.core.config import get_settings
from app.db.connection import connect
from scripts.migrate_db import apply_migrations

with connect(get_settings(), row_factory=None) as connection:
    print(apply_migrations(connection, Path('../infrastructure/postgres/init')))
PY
```

`init_db.py`는 여전히 `002`만 적용하는 이전 초기화 도구입니다. 최신 기능 준비에는
이 도구나 개별 SQL 직접 실행 대신 전체 runner를 사용합니다.

### 이력이 없는 기존 DB의 전환

앱 테이블이 있는데 migration 이력이 없거나 `001`~`013` baseline 기록이 빠져 있으면 runner가 중단합니다.
이때 오류를 우회해 전체 SQL을 다시 실행하거나 임의의 체크섬으로 적용 이력을 채우면 안 됩니다.

1. 기존 DB를 백업하고 격리된 DB로 복원하여 자료·관계가 보존되는지 확인합니다.
2. 실제 스키마와 데이터 변환 결과를 `001`~`013` 및 당시 배포 버전과 대조합니다. 모르는 적용 상태는 미확인으로 둡니다.
3. 이미 적용됐음을 확인한 파일만 운영 변경 승인 후 정확한 파일 SHA-256과 함께 baseline에 기록합니다. 부분 적용 상태는 별도 전환 계획으로 해결하며 미적용 파일을 적용 완료로 표시하지 않습니다.
4. `python scripts/migrate_db.py --preflight`를 통과한 뒤 같은 검증 SHA를 배포합니다. 이후 `014` 등 미적용 migration만 실행됩니다.

baseline 자동 승인 도구와 실제 운영 복원 검증은 이번 변경에 포함되지 않습니다.

### 수집 보호·근거 검토·상태 확인 DB 통합 테스트

`backend/tests/test_github_preservation_postgres.py`, `backend/tests/test_github_items_postgres.py`, `backend/tests/test_project_lifecycle_postgres.py`는 `WORKTRACE_TEST_DATABASE_URL`이 있을 때만 실행됩니다.
데이터베이스 이름은 반드시 `worktrace_test`여야 하며 임의 스키마 안에서 검증 후 rollback합니다. 독립 연결을 사용하는 동시 요청 테스트는 임시 스키마를 커밋한 후 해당 스키마만 제거합니다. 같은 테스트 DB에서 여러 suite를 동시에 실행하지 않습니다.
GitHub Actions는 격리된 pgvector 테스트 서비스를 사용합니다. 환경변수가 없는 로컬 테스트에서는 이 검증이 skip됩니다.
운영 URL을 테스트 변수에 넣지 않습니다. 테스트는 개발자의 `.env`를 읽지 않으며, 필요한 설정은 테스트 환경 또는 fixture로 주입합니다.

GitHub 근거 UI 브라우저 검증은 별도로 설치된 Playwright로 실행합니다. 애플리케이션 런타임 의존성은 추가하지 않았습니다.

```bash
cd frontend
WORKTRACE_BROWSER_URL=http://127.0.0.1:3100 \
WORKTRACE_PLAYWRIGHT_PATH=/absolute/path/to/playwright/index.mjs \
node scripts/github-evidence.browser.mjs
```

필요하면 `WORKTRACE_CHROME_PATH`로 Chrome 실행 파일을 지정합니다. 이 테스트는 API를 모의 응답으로 대체하며 실서비스 자료를 쓰지 않습니다. 320/390/768/1440px 캡처, 넘침·버튼 겹침, 채택/연결/제외/복원, 충돌, 조회 실패, 응답 유실 재시도를 검증합니다. 실제 SQL 검증 및 운영 smoke를 대체하지 않습니다.

같은 환경에서 `node scripts/project-lifecycle.browser.mjs`는 개발·운영 상태 확인, 미완료 사유, 재개, 이력, 충돌 재조회, 응답 유실 재시도와 대시보드·프로젝트 목록의 반응형 배치를 검증합니다. 상태 패널의 입력은 같은 프로젝트 탭 이동 중 유지하지만 새로고침·다른 프로젝트 이동까지 복원하지는 않습니다.

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

백업 파일은 기본적으로 `backups/postgres/worktrace_YYYYMMDDTHHMMSSZ.dump`
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
scripts/restore_local.sh --confirm backups/postgres/worktrace_YYYYMMDDTHHMMSSZ.dump
```

현재 데이터를 보존해야 한다면 복원 전에 새 백업을 먼저 만듭니다.

### 예약 백업

`backup_scheduled.sh`는 동시 실행을 차단하고 백업 성공 후 보존 기간이 지난
dump를 정리합니다. 기본 보존 기간은 14일입니다.

```bash
BACKUP_RETENTION_DAYS=14 scripts/backup_scheduled.sh
```

운영 서버에서는 이 명령을 systemd timer 또는 cron으로 하루 한 번 실행하고,
실패 종료 코드를 모니터링 대상으로 연결합니다. Oracle Cloud 배포 단계에서는
생성된 dump를 별도 Object Storage bucket으로 복제한 후 복원 리허설을 수행해야
합니다.

운영 환경에서는 암호화 키 파일이 필수입니다. 키 파일은 repository 밖에 `600`
권한으로 만들고 환경변수에는 파일 경로만 지정합니다. 키 자체를 `.env`나 GitHub에
저장하지 않습니다.

```bash
APP_ENV=production \
COMPOSE_FILE=docker-compose.prod.yml:docker-compose.oracle.yml \
COMPOSE_ENV_FILES=.env.production \
BACKUP_ENCRYPTION_KEY_FILE=/home/ubuntu/.config/worktrace/backup.key \
BACKUP_RETENTION_DAYS=14 \
scripts/backup_scheduled.sh
```

암호화 백업은 `.dump.enc`로 생성됩니다. 복원 시 같은 키 파일 경로를 지정하면
임시 평문 dump를 자동으로 정리합니다.

```bash
BACKUP_ENCRYPTION_KEY_FILE=/home/ubuntu/.config/worktrace/backup.key \
COMPOSE_FILE=docker-compose.prod.yml:docker-compose.oracle.yml \
COMPOSE_ENV_FILES=.env.production \
scripts/restore_local.sh --confirm backups/postgres/worktrace_YYYYMMDDTHHMMSSZ.dump.enc
```

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

- `[user_project_seed] worktrace`
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
curl -H "X-Worktrace-Owner-Id: local-owner" \
  -H "X-Worktrace-Report-Token: dev-only-report-token" \
  http://localhost:8000/projects
```

프로젝트와 업무를 API로 직접 확인하려면 다음처럼 호출합니다.

```bash
PROJECT_ID=$(curl -sS -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -H "X-Worktrace-Owner-Id: local-owner" \
  -H "X-Worktrace-Report-Token: dev-only-report-token" \
  -d '{"title":"v0.1 실행 점검","status":"in_progress","description":"로컬 사용 흐름 확인"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://localhost:8000/projects/${PROJECT_ID}/tasks" \
  -H "Content-Type: application/json" \
  -H "X-Worktrace-Owner-Id: local-owner" \
  -H "X-Worktrace-Report-Token: dev-only-report-token" \
  -d '{"title":"첫 업무 등록","status":"planned","priority":"high","due_date":"2026-06-07"}'

curl -sS http://localhost:8000/projects/${PROJECT_ID} \
  -H "X-Worktrace-Owner-Id: local-owner" \
  -H "X-Worktrace-Report-Token: dev-only-report-token"
```

### Weekly report API

아래 날짜와 토큰은 로컬 요청 형식 예시입니다. 실제 조회 기간과 설정한 토큰으로 변경합니다.

```bash
curl -X POST http://localhost:8000/reports/weekly \
  -H "Content-Type: application/json" \
  -H "X-Worktrace-Owner-Id: local-owner" \
  -H "X-Worktrace-Report-Token: dev-only-report-token" \
  -d '{"start_date":"2026-06-01","end_date":"2026-06-07"}'
```

현재 리포트 화면은 `/reports/automatic`을 사용합니다. `report_type`은 `daily`,
`weekly`, `monthly`이며 시작/종료일을 포함해 각각 1일, 최대 7일, 최대 32일을
허용합니다. 저장된 자료를 집계하는 경로로 OpenAI 호출이나 예약 실행은 하지 않습니다.
월간 성과와 진척 제안은 후보이며 프로젝트 상태·확정 성과를 자동 수정하지 않습니다.

### Frontend → Backend proxy 확인

프론트엔드 실행 후 브라우저에서 <http://localhost:3000/projects>를
열어 프로젝트 목록이 로딩되는지 확인합니다. 문제가 있으면 다음을
확인하세요.

- Docker 전체 실행: 루트 `.env`의 `WORKTRACE_BACKEND_URL=http://backend:8000`
- 로컬 frontend 실행: `frontend/.env.local`의 `WORKTRACE_BACKEND_URL=http://localhost:8000`
- Backend CORS origin: `FRONTEND_ORIGIN=http://localhost:3000`
- Backend health: <http://localhost:8000/health>

## 개발 검증 명령

로고 원본은 `frontend/public/brand/worktrace-mark.svg`입니다. 헤더와 로그인은 같은 파일을 사용하며,
favicon과 Apple 아이콘을 갱신할 때는 frontend 의존성 설치 후 다음을 실행합니다.
Next.js가 설치하는 기존 `sharp`를 사용하며 별도 디자인 서비스나 API 키는 필요하지 않습니다.

```bash
cd frontend
node scripts/generate-brand-assets.mjs
```

생성된 `public/favicon.ico`와 `public/apple-touch-icon.png`도 배포 자산으로 포함합니다.
실제 화면은 SVG, ICO, Apple 아이콘을 metadata에 등록하며 해당 파일만 로그인 없이 제공합니다.

```bash
# Backend tests
cd backend
source .venv/bin/activate
pytest -q
cd ..

# Frontend checks
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build

# Compose syntax/services
docker compose config --services
```

## 자주 겪는 문제

### `relation "project_tasks" does not exist`

DB volume이 오래되어 최신 SQL이 적용되지 않은 상태일 수 있습니다. 백업 후 전체 migration을 적용합니다.

```bash
docker compose exec -T backend python scripts/migrate_db.py
```

### 3000 또는 8000 포트 충돌

Docker Desktop에서 `worktrace` 프로젝트 밖의 컨테이너나 로컬
`node`/`uvicorn` 프로세스가 같은 포트를 잡고 있으면 하나로 통일합니다.

```bash
# 3000 포트를 잡고 있는 로컬 프로세스 확인
lsof -nP -iTCP:3000 -sTCP:LISTEN

# worktrace Compose 컨테이너만 다시 실행
docker compose down
docker compose up -d --build
docker compose ps
```

다른 로컬 프론트엔드를 동시에 띄워야 할 때만 루트 `.env`에서
`FRONTEND_PORT`를 바꾸고 Compose를 재실행합니다. 기본 운영은
`worktrace` Compose 프로젝트 하나로 `db`, `backend`, `frontend`를
함께 관리하는 방식입니다.

### 프론트에서 API 오류가 표시됨

1. `curl http://localhost:8000/health`로 백엔드가 떠 있는지 확인합니다.
2. Docker 실행이면 루트 `.env`, 로컬 실행이면
   `frontend/.env.local`의 `WORKTRACE_BACKEND_URL`을 확인합니다.
3. 리포트 API는 `WORKTRACE_REPORT_TOKEN` /
   `REPORT_ACCESS_TOKEN` 값이 일치해야 합니다.

## 현재 아키텍처 tradeoff

이 저장소는 단일 사용자용 로컬/클라우드 서비스 구조입니다.
아래 경계는 다중 사용자·고가용성 운영으로 확장하기 전에 검토해야 합니다.

- **접근 가드**: 서명된 HttpOnly 세션으로 단일 사용자 프론트 접근을
  보호하고 Next.js 서버 라우트가 owner/token을 백엔드에 주입합니다. 다중
  사용자별 데이터 권한을 판정하는 인증 모델은 아니므로 개인 배포 범위를
  넘기기 전에 owner-scoped identity 연동이 필요합니다.
- **상태값 계약**: 프로젝트/업무/리포트 상태값은 SQL check constraint,
  Pydantic schema, frontend type/label map에 명시적으로 반복되어 있습니다.
  MVP에서는 변경 지점을 눈에 보이게 두기 위한 선택이며, 상태값이
  늘어나기 전 공통 contract 또는 생성 방식으로 정리합니다.
- **스키마 관리**: 번호가 붙은 SQL migration과 체크섬 기반 runner를
  사용합니다. 이미 적용된 migration은 수정하지 않고 새 파일로 변경을
  누적합니다.

## 현재 v0.1 범위에서 하지 않은 것

- 문서 업로드·텍스트 추출·AI 문서 분석
- 문서 청크 검색·임베딩·근거 기반 Q&A
- 자동 롤백, 무중단 배포, 기존 운영 DB baseline·복원 검증
- 전체 WBS 승인 계획·버전 모델, 개인 기여·완료 전이 이력
- 원격 백업 자동 복제·복원 리허설 자동화
- Issue·PR 변경 이벤트의 실시간 동기화와 GitHub 이력 정기 동기화 스케줄러
- 다중 사용자 인증과 owner-scoped 권한 체계

## 저장소 관리

`.env*` 실제 설정, 백업, 빌드 산출물과 `/.omx/metrics.json`은 `.gitignore`로 제외합니다.
`metrics.json`은 개발 도구의 자동 활동 기록이며 애플리케이션 데이터나 설정이 아닙니다.
이미 추적된 파일은 ignore 규칙만으로 제외되지 않아 Git 추적도 해제하되 로컬 파일은 유지합니다.
`.omx`의 과거 계획·검증 기록은 당시의 이력으로 보존하며 현재 기능 명세는 이 README와 디자인 문서입니다.
기존 DB 볼륨명·migration 파일명·호환 환경변수의 `work-support`/`work_support`는
데이터 및 체크섬 호환을 위한 것으로 일괄 이름 변경하지 않습니다.

## 보안 주의

- 실제 secret은 비공개 환경 파일이나 GitHub Actions secrets에서 관리하고 커밋하지 않습니다.
- `.env.example` 파일은 placeholder만 제공합니다. DB 비밀번호, report token,
  OpenAI key는 실제 `.env` / `.env.local` / `.env.production` 등 비공개 설정에만 입력합니다.
- 외부 네트워크에 노출하기 전에 운영용 DB 비밀번호, report token, session
  secret, 로그인 hash, HTTPS origin을 각각 고유한 값으로 설정해야 합니다.
- 업로드 원본 파일은 추후에도 public 경로에 직접 노출하지 않는 구조를 유지합니다.
