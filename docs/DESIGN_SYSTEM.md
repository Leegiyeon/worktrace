# worktrace Design System

worktrace UI는 실무형 개인 프로젝트 관리 도구를 기준으로 한다. 현재 구현은 데이터, 근거, 명시적 상태, compact control, 낮은 장식성을 우선한다. 이 문서는 구현된 상태와 설계 의도를 구분해 기록한다.

최종 대조: 2026-09-18. 제품 흐름은 [DESIGN.md](../DESIGN.md), 데이터·운영 기준은 [README.md](../README.md)를 참조한다.

## 1. 현재 구현 스냅샷

- Framework: Next.js App Router, React, TypeScript, global CSS, route/component CSS module.
- 주요 route: `/`, `/projects`, `/projects/[projectId]`, `/goals`, `/verifications`, `/branches`, `/insights`, `/reports`, `/login`.
- 전역 navigation: logo는 dashboard(`/`)로 이동하고, header는 프로젝트, 목표·마일스톤, 완료 검토, 브랜치 그래프, 인사이트, 리포트를 노출한다. `/login`에서는 header를 숨긴다.
- 브랜치 그래프: 한 번에 하나의 selected project만 검사한다. native `프로젝트` select와 프로젝트 링크를 같은 toolbar에 두고, selected repository만 fetch한다.
- 진행률: `counts_toward_progress=true`인 WBS만 계산한다. 산정 대상이 있고 모두 마일스톤에 배정되면 가중 평균을 사용한다. 미배정 업무가 하나라도 있으면 전체 WBS 완료 비율을 사용하며, 산정 대상이 없으면 `산정 전`으로 표시한다.
- 완료 검토(`/verifications`): 프로젝트 한 개를 선택하여 성취 기준·남은 WBS·실제 근거와 저장된 확인 상태를 먼저 본다. AI 검토는 요청 시 실행하는 판단 보조이며 테스트 실행이나 서비스 상태 감시가 아니다. stale/current review를 구분하고, `성취 기준 확인 · 검증 완료`는 사용자의 별도 명시 확인 flow다.
- 데이터 출처: 공통 progress formatter는 자동 구성 WBS 포함 시 `참고 N%`, 출처 필드 누락 시 `기준 미확인`을 표시한다. 두 경우 모두 평균에서 제외한다. 프로젝트 상태와 계산된 WBS 비율을 동일시하지 않는다. 상세에서는 `수치 산정 근거`를 펼쳐 분모·분자·출처·계산식을 확인한다.
- AI confidence는 객관적 정확도 백분율로 노출하지 않는다. 수정일 기반 목록은 완료일로 표기하지 않고, 조회된 커밋 수를 전체 저장 건수로 표현하지 않는다.
- 브랜드: `frontend/public/brand/worktrace-mark.svg`가 단일 원본이다. 녹색 `#126B5C` 바탕의 흰 W 경로와 금색 `#F2BE5C` 최신 지점을 사용한다. 헤더 34px, 로그인 40px로 고정하고 모바일에서는 심볼만 유지한다. 아이콘 색을 전체 UI 팔레트로 확장하지 않는다.
- favicon은 같은 원본에서 생성한 16/32/48px ICO, SVG, 180px Apple 아이콘을 사용한다. 로그인 전에도 이 자산만 공개하고 인증된 API의 접근 정책은 바꾸지 않는다.
- Page chrome: 여러 기존 화면은 `.dashboard-topbar`를 아직 사용한다. 브랜치 그래프 화면은 장식 card/eyebrow 없이 compact header를 사용한다.
- 프로젝트 `GitHub 근거`: 검토 대기·업무 연결·제외·전체 필터와 20개 페이지 목록. 한 원본만 펼쳐 본문·수집/수정 시각·업무 채택 또는 연결을 처리한다. 원본 상태와 로컬 업무 상태는 별개다. 제외/복원은 원본 삭제가 아니다.
- 근거 검토 입력: 같은 프로젝트 내 탭 이동 시 유지한다. 저장 실패는 입력과 요청 ID를 보존하고, 409 충돌은 최신 원본 재확인을 요구한다. 응답 유실 뒤 목록에서 빠진 항목도 재시도할 수 있다. 완료 후 WBS 수치만 갱신하고 다른 폼은 초기화하지 않는다.

## 2. UI 원칙

1. 설명보다 업무 판단에 필요한 데이터를 먼저 보여준다.
2. 장식성 hero, 반복 subtitle, 불필요한 helper text를 줄인다.
3. 주요 정보는 metric, table, board, dense list, badge, progress bar, functional graph로 표현한다.
4. 무거운 시각화는 selected context 하나에만 bounded surface로 제공한다.
5. loading, empty, disconnected, partial failure, error, success, stale, refreshing, saving, disabled 상태를 구분한다.
6. navy/neutral 계열을 기본으로 하고 semantic color는 상태 전달에만 사용한다.
7. 한국어 업무 용어와 짧은 command label을 유지한다.
8. 기존 token과 primitive로 해결하고 새 visual system이나 dependency를 만들지 않는다.

## 3. Token

Source of truth: `frontend/app/globals.css`.

### Color

- `--background`: `#f5f6f8`
- `--foreground`: `#111827`
- `--muted`: `#647084`
- `--surface`: `#ffffff`
- `--surface-muted`: `#f1f4f8`
- `--surface-elevated`: `rgba(255, 255, 255, 0.88)`
- `--accent`: `#172033`
- `--accent-strong`: `#0b1220`
- `--accent-soft`: `#e6edf7`
- `--accent-blue`: `#2367e8`
- `--border`: `#d9e0ea`
- `--danger`: `#b42318`
- `--success`: `#15803d`
- `--warning`: `#b7791f`

### Typography

- Sans stack: `-apple-system`, BlinkMacSystemFont, `SF Pro Text`, `Segoe UI`, `Noto Sans KR`, Arial, Helvetica, sans-serif.
- Mono stack: `SFMono-Regular`, Consolas, `Liberation Mono`, monospace.
- Text token: `--text-xs 11px`, `--text-sm 12px`, `--text-md 13px`, `--text-base 14px`, `--text-lg 16px`.
- 기본 page `h1`은 28px이고, compact route header는 module CSS에서 22px까지 낮출 수 있다.
- letter spacing은 `0`이고 viewport width로 font-size를 scale하지 않는다.

### Spacing / Radius / Elevation

- `--page-gutter`: `clamp(12px, 2.5vw, 32px)`.
- `.page-shell`: max-width 1384px.
- 주요 gap은 8, 10, 12, 14, 16px 단위를 사용한다.
- 기본 control height는 40px, compact control height는 32px.
- radius는 6-8px 범위다.
- shadow는 `--shadow-soft`, `--shadow-card`, `--shadow-hairline` 정도로 제한한다.

## 4. Navigation / Page Chrome

- logo는 `aria-label="worktrace 대시보드로 이동"`을 가진 dashboard link다.
- top-level route link는 active 상태에서 `aria-current="page"`를 사용한다.
- 760px 이하에서는 header nav를 `화면 이동` native select로 바꾼다. 대시보드와 모든 최상위 화면을 선택할 수 있고 프로젝트 상세는 프로젝트로 표시한다.
- 설계 의도: inspector/tool 성격의 화면에는 decorative eyebrow나 큰 topbar card를 새로 추가하지 않는다.
- 구현 상태: `.dashboard-topbar`는 유지하되 배경·테두리·그림자를 없앤 공통 제목 행이다. `.dashboard-metrics`는 데스크톱 4열, 640px 이하 2열의 구분선 요약이다.

## 5. Layout Pattern

### Page Shell

- route content는 `.page-shell`을 사용한다.
- route-local layout은 CSS module을 우선한다.
- route-level gap은 compact하게 유지한다.

### Grid / Table / List

- dashboard는 데스크톱 2열, 모바일 1열의 named grid area를 사용한다. 프로젝트 현황과 이슈를 우선하며 지연 업무는 이슈 목록에 통합한다.
- 프로젝트와 이슈 행은 전체 로드 결과를 유지하고 각각 최대 360px(모바일 300px) 안에서 스크롤한다. 목록이 길면 키보드 포커스도 제공한다.
- metric row는 `.summary-grid`와 `.metric-card`를 사용한다.
- 일반 table은 `.data-table-wrap`으로 horizontal overflow를 관리한다. WBS는 720px 이하에서 제목 한 행과 2열 필드로 전환한다. 이 규칙을 다른 탭 테이블에 적용하지 않는다.
- dense list는 desktop에서 한 줄 비교를 우선하고 mobile에서 column으로 접는다.
- 긴 title, evidence, repository name, URL, commit message는 wrap 또는 clamp 처리한다.

### Panel / Card

- `.panel`은 framed tool, 반복 item, 상태/action grouping에 사용한다.
- 설계 의도: 장식 목적의 card-in-card는 만들지 않는다.
- 구현 상태: milestone evidence나 AI review처럼 별도 disclosure/result 의미가 있는 nested panel은 존재한다. 새 작업에서는 같은 의미적 경계가 있을 때만 유지한다.
- empty panel은 긴 설명 대신 짧은 state와 필요한 action만 둔다.

## 6. Component Contract

### Metric / Badge

- metric은 값과 단위를 먼저 보여주고 label은 짧게 둔다.
- `status-pill`, `meta-pill`, `count-badge`는 상태, 우선순위, count, stale/current review, compact summary에 사용한다.
- narrow width에서 badge가 줄바꿈되어도 읽을 수 있어야 한다.

### Form / Action

- input, select, primary command button은 기본 40px 높이다.
- table/nav control은 필요하면 32px compact 높이를 쓴다.
- 목표, 성취 기준, 근거, 성과처럼 긴 값은 textarea를 우선한다.
- button label은 결과 중심으로 쓴다: `프로젝트 추가`, `목표 저장`, `AI 검토`, `성취 기준 확인 · 검증 완료`, `리포트 생성`.
- 프로젝트 생성과 WBS 추가/수정은 필요할 때만 폼을 연다. WBS 편집은 항목명으로 포커스를 이동하며 양식을 숨겨도 같은 페이지의 초안을 보존한다.
- WBS 기본 보기는 목록이며 탭·보기·필터·정렬은 URL을 따른다. 프로젝트 목록의 검색·상태·정렬도 URL에 보존한다. 새로고침 시 입력 초안까지 보존하는 기능은 아니다.

### Alert / Status

- error는 `.alert.error`와 `role="alert"`를 사용한다.
- success/copy/status는 `.alert.success`, `role="status"`, `aria-live`를 사용한다.
- partial load failure와 valid empty state를 섞지 않는다.

### Branch Graph

- branch page는 project selection과 selected repository fetch state를 소유한다.
- 모든 project repository를 upfront fetch하지 않는다.
- graph component는 selected project title, repository label, source timestamp, refresh, compact/full commit mode, selected commit detail, incomplete-history note, branch status disclosure를 소유한다.
- 요약은 실제 가용 폭으로 노드 간격을 계산한다. 라벨 글자 크기는 유지하고 실제 글자 폭을 측정한다. 같은 HEAD의 이름은 대표 이름과 `+N`으로 묶으며 선택하면 전체 브랜치 상태를 연다.
- 라벨 행은 커밋 경로 행과 별도로 배치한다. 요약 높이는 내용에 맞추고 전체 커밋 보기만 176px(모바일 160px)의 스크롤 영역을 사용한다. 부모 연결과 조회 범위 밖 표시를 생략하거나 만들어내지 않는다.
- repository fetch error, disconnected repository, graph loading, empty branch history, retry/refresh는 별도 상태다.
- page title은 `브랜치 그래프`이고, selected project title은 graph component가 표시한다. progress나 project heading을 주변에서 중복하지 않는다.

### Goals / Milestone

- goals page는 project objective와 success criteria 편집을 소유한다.
- 한 프로젝트를 선택해 목표·성취 기준과 마일스톤부터 조회한다. `목표 편집`으로 입력을 열고 미저장 프로젝트는 선택 메뉴에도 표시한다.
- 저장은 해당 프로젝트 응답만 적용하며 다른 draft와 저장 중 추가 입력을 보존한다. 루트 `GoalDraftProvider`가 현재 탭의 메모리에 초안과 서버 기준값을 유지해 앱 내부 이동·뒤로/앞으로 이동에도 보존한다.
- 미저장 상태의 내부 링크/모바일 메뉴는 이동 여부를 확인한다. 브라우저 history를 변조해 뒤로 가기를 막지 않는다. 탭 닫기·새로고침은 native 경고를 사용하며 강제로 이동하면 메모리 초안은 사라진다. 영구 저장소·새 탭·브라우저 재시작 복원은 지원하지 않는다.
- 로그아웃은 API 호출 전에 확인하고 성공 응답 후 초안을 비운다. 실패 시 입력을 유지한다.

### Work Log Timeline

- 최신 수행일 순으로 원래 업무명을 표시하고 검색/유형 필터를 제공한다. 업무명 유사도로 WBS 제목을 대신 표시하지 않는다.
- 추가/수정 폼은 필요할 때만 표시하며 같은 폼을 재사용한다. 업무명·수행일·유형·내용을 먼저 입력하고 결정·협업자·다음 액션·블로커·소요 시간은 상세 입력에 둔다.
- 양식 숨김과 프로젝트 상세 탭 전환은 초안을 유지한다. 로그 저장/삭제는 해당 API 결과만 적용한다. 다른 프로젝트/전역 경로 이동까지 로그 초안을 보존하는 기능은 이번 범위에 포함하지 않는다.
- 목표/검증센터는 프로젝트·마일스톤·저장된 검토 조회 실패를 빈 상태로 표시하지 않으며 개별 재시도를 제공한다.
- milestone row는 title, acceptance criteria, WBS completion, progress, weight, `근거 보기`를 보여준다.
- evidence disclosure는 WBS completion, evidence count, AI review action/result, acceptance criteria, pending WBS, recent commit/PR evidence를 보여준다.
- AI review는 완료 상태를 직접 바꾸지 않는 판단 보조로 표현한다.
- progress 표기는 milestone/WBS 기반 또는 `산정 전`으로 표현하고 raw activity volume처럼 다루지 않는다.

### Verification Center

- project card는 progress, milestone count, valid AI review count, needed review count, batch action을 보여준다.
- 기본 batch review는 missing/stale review만 AI 호출한다. force review는 명시적 action이다.
- 마일스톤 또는 저장된 검토 조회가 실패한 프로젝트에서는 일괄 실행을 비활성화하고 조회 복구를 우선한다.
- validation done milestone은 batch AI review에서 유지된다.
- stale persisted review는 stale reason과 함께 보이지만 validation 완료 action을 unlock하지 않는다.
- `성취 기준 확인 · 검증 완료`와 취소는 사용자의 별도 확인 flow다. 이는 progress 계산식 자체의 전역 prerequisite이 아니다.

## 7. Accessibility

- 가능한 경우 native control을 사용한다. project selection은 visible label `프로젝트`가 있는 native select다.
- form control은 visible 또는 programmatic label을 가진다.
- `aria-current`, `aria-expanded`, `aria-pressed`, `aria-busy`, `role="status"`, `role="alert"`, `aria-live`를 상태에 맞게 사용한다.
- link, button, input, select, textarea, graph canvas, graph commit node는 focus state가 보여야 한다.
- table은 semantic table을 유지한다.
- 색상만으로 상태를 전달하지 않는다.

## 8. Responsive / Overflow

- 문서 최소 폭은 320px이고 설계 target은 mobile 360px까지 포함한다.
- global overflow hardening은 `frontend/app/ui-overflow-fixes.css`에 있다.
- header nav, dense table, graph canvas는 필요한 경우 각자 내부 scroll을 가진다.
- milestone row는 900px/640px 근처에서 action을 full-width로 접어 overlap을 피한다.
- verification action과 panel-title action row는 mobile에서 줄바꿈된다.
- count badge와 pill은 아주 좁은 화면에서 wrapping을 허용한다.

## 9. Screen Contract

### Dashboard

- active projects, attention tasks, delayed work, recently completed work, recent logs, status graph, quick capture를 보여준다.
- quick capture의 AI draft는 보조이며, 제출 source는 사용자가 확인한 form 값이다.

### Projects

- summary는 active count, total projects, remaining tasks, average progress를 보여준다.
- 생성 form과 project table을 같은 page에서 관리한다.

### Project Detail

- project CRUD, WBS/tasks, work logs, outcomes, repository connection/status, commits, deliveries, branch graph, career assets를 소유한다.
- record type별 관리 surface는 중복하지 않는다.
- 성과는 후보/검토 중/확정 중 하나의 목록만 표시하고, 선택 시 목록 자리에 검토 폼을 연다. 상태 건수는 단계 선택에 통합해 별도 지표 카드를 반복하지 않는다.
- 근거 로그는 검색·체크 선택·선택한 항목 필터와 원문 펼침을 제공한다. 성과 내용/근거 수정은 확정 체크를 해제하며, 사용자가 다시 확인한 값만 `resume_ready=true`로 저장한다. 기존 문서 근거 연결은 편집 시 지우지 않는다.
- 경력 자산은 생성일 최신 버전을 기본으로 하나만 표시한다. 버전 선택과 생성 조건은 결과 위 도구줄에 통합하고, 편집은 요청 시에만 연다. 편집 중 복사는 현재 초안이며 저장/생성 실패는 초안을 보존한다.
- 성과의 목록/같은 프로젝트 탭 전환은 작성 값을 보존하고, 다른 성과로 대체/작성 취소 시 변경 유실을 확인한다. 경력 자산의 버전 전환/생성/편집 취소도 변경 유실을 확인한다. 전역 경로 이동·브라우저 재시작 보존 기능과는 구분한다.

### Goals / Milestones

- objective/success criteria 편집과 milestone evidence 검토를 소유한다.
- progress는 counted WBS와 milestone weight의 계산 결과로 표시한다.

### Verification Center

- AI-assisted milestone review와 explicit validation state 변경을 소유한다.
- AI batch review를 milestone 자동 완료로 설명하지 않는다.

### Branch Graph

- 한 selected project의 repository branch inspection을 소유한다.
- page title은 `브랜치 그래프`이고 graph component가 selected project title을 표시한다.
- graph 주변에 progress나 selected project heading을 중복하지 않는다.

### Insights

- 사용자가 project를 선택하고 실행 버튼을 눌렀을 때만 Project Analyst가 실행된다.
- 결과는 objective, WBS, milestone, GitHub evidence 기반의 advisory output이다.

### Reports

- date/type control은 생성 전 validation한다.
- 생성 결과는 metric, evidence table/list, Markdown preview, copy action 중심이다.

## 10. Review Checklist

- [ ] 현재 navigation과 route ownership을 반영했는가?
- [ ] 구현 상태와 설계 의도를 구분했는가?
- [ ] loading, empty, disconnected, partial failure, error, success 상태가 구분되는가?
- [ ] 무거운 graph/visualization이 selected context 하나로 bounded 되는가?
- [ ] AI review가 자동 완료가 아니라 advisory로 표현되는가?
- [ ] progress 설명이 counted WBS ratio / weighted milestone average와 일치하는가?
- [ ] decorative card-in-card를 새로 만들지 않았는가?
- [ ] 현재 CSS token을 재사용했는가?
- [ ] desktop/mobile에서 overlap, clipping, 과한 nowrap이 없는가?
- [ ] label, focus, status role, semantic table/disclosure를 유지했는가?
