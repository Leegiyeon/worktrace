# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-09-14
- Primary product surfaces: login, dashboard, project list, project detail, goals/milestones, verification center, branch graph, insights, reports
- Evidence reviewed: `AGENTS.md`, `docs/DESIGN_SYSTEM.md`, `frontend/app/globals.css`, `frontend/app/ui-overflow-fixes.css`, `frontend/app/components/AppHeader.tsx`, `frontend/app/components/AppLogo.tsx`, `frontend/app/page.tsx`, `frontend/app/projects/page.tsx`, `frontend/app/projects/[projectId]/page.tsx`, `frontend/app/goals/page.tsx`, `frontend/app/verifications/page.tsx`, `frontend/app/branches/page.tsx`, `frontend/app/projects/[projectId]/BranchActivityGraph.tsx`, `frontend/app/insights/page.tsx`, `frontend/app/reports/page.tsx`, and current frontend contract tests under `frontend/scripts/`
- Evidence boundary: this document records current implementation separately from intended design direction; unimplemented future behavior stays in Open questions or Implementation constraints.

## Brand
- Personality: quiet, precise, work-focused, and trustworthy
- Trust signals: evidence-linked outcomes, explicit loading/error/status states, owner-scoped API proxy boundaries, current-vs-stale AI review labels, and no fabricated metrics
- Avoid: marketing copy, decorative hero layouts, duplicated subtitles, oversized chart surfaces, all-project graph stacks, disabled feature promises, and placeholder panels with explanation but no data

## Product goals
- Implemented goals: capture and review project/WBS progress, connect GitHub repository evidence, inspect branch activity for one selected project, manage milestone evidence and AI review assistance, generate reports, and edit career assets from confirmed project records
- Design intentions: keep progress based on planned WBS ratios and assigned milestone weighting rather than raw commit count; keep AI as decision support until the user confirms explicit validation state changes.
- Non-goals: multi-user SaaS, public sharing, OCR, document RAG, advanced WBS import, and broad organization administration in the current MVP
- Success signals: a project exposes its planned work, evidence, validation state, branch activity, reports, and career reuse material without requiring the user to reconcile duplicate sources of truth

## Personas and jobs
- Primary personas: one knowledge worker managing personal project evidence and career history
- User jobs: decide what needs attention, record completed work, inspect GitHub evidence, confirm milestone completion, preserve decisions/blockers, generate weekly/monthly reporting, and reuse career statements
- Key contexts of use: daily desktop review, quick mobile capture, weekly reporting, milestone validation sessions, branch/evidence inspection, and periodic resume preparation

## Information architecture
- Implemented primary navigation: the logo links to `/`; the authenticated header exposes `/projects`, `/goals`, `/verifications`, `/branches`, `/insights`, and `/reports`; `/login` hides the app header.
- Navigation state: desktop global links set `aria-current="page"`; at 760px and below a native `화면 이동` select exposes all seven routes including the dashboard. Project detail maps to the projects option. The branch page keeps its project selector inside the page toolbar.
- Core routes/screens: `/login`, `/`, `/projects`, `/projects/[projectId]`, `/goals`, `/verifications`, `/branches`, `/insights`, and `/reports`.
- Content hierarchy: dashboard attention and activity first; project list/detail for CRUD and evidence; goals/milestones for objective and acceptance criteria; verification center for AI-assisted review and explicit validation state; branch graph for selected repository inspection; insights and reports after project records exist.
- Workflow sequence: define project and WBS -> connect repository/evidence -> review goals and milestone evidence -> use AI review as advisory output -> explicitly confirm validation state when needed -> use computed progress, reporting, and career assets without treating AI as the source of truth.

## Design principles
- Action before summary: overdue, due-soon, and next-action records precede aggregate charts.
- Evidence before generation: AI outputs follow project records, WBS, commits, work logs, outcomes, and milestone evidence.
- One selected context for heavy visuals: branch activity renders one selected project/repository graph, not an all-project stacked dashboard.
- Progressive disclosure: common fields stay visible; branch details, milestone evidence, and secondary evidence lists use compact disclosure or bounded panels.
- One action, one place: global navigation owns route movement, project tabs own domain workflows, and record rows/cards expose edit/delete/validation actions in their local context.
- Honest scope: stale AI reviews remain visible but cannot complete validation; verified milestones are not overwritten by batch AI calls; unavailable data is shown as loading, empty, error, or disconnected rather than implied success.
- Tradeoffs: desktop keeps dense tables, boards, and metric grids; mobile WBS uses labeled two-column fields with a full-width title. Other dense tables retain bounded horizontal overflow where needed.

## Visual language
- Color: implemented tokens use neutral light surfaces with navy identity accents: `--background #f5f6f8`, `--foreground #111827`, `--muted #647084`, `--surface #ffffff`, `--surface-muted #f1f4f8`, `--accent #172033`, `--accent-strong #0b1220`, `--accent-soft #e6edf7`, `--accent-blue #2367e8`, `--border #d9e0ea`, `--danger #b42318`, `--success #15803d`, and `--warning #b7791f`.
- Typography: shared system sans stack with `SF Pro Text`, `Segoe UI`, `Noto Sans KR`, Arial, and Helvetica; mono stack for commit SHAs; compact fixed text tokens from `--text-xs 11px` through `--text-lg 16px`; no viewport-scaled type; letter spacing `0`.
- Spacing/layout rhythm: compact 8px-derived rhythm; `--page-gutter: clamp(12px, 2.5vw, 32px)`; `.page-shell` max width 1384px; dense grids use 10-12px gaps.
- Shape/radius/elevation: implemented radii are `--radius-lg 8px`, `--radius-md 8px`, `--radius-sm 6px`; panels and cards use restrained borders plus soft/hairline shadows.
- Motion: small hover/focus transitions for controls and cards; reduced-motion CSS disables transitions and animations.
- Imagery/iconography: no decorative imagery; the logo uses an inline SVG mark; branch graph uses SVG lines/nodes as functional data visualization.

## Components
- Existing components to reuse: metric cards, status/meta/count badges, dense lists, data tables, progress bars, task boards, panel title rows, tab navigation, alerts, forms, and compact action rows.
- Dashboard hierarchy: project progress and one filtered attention queue precede activity charts and recent logs. Overdue tasks are part of that queue, not a duplicate panel. Project/issue lists keep all loaded rows in bounded scroll regions.
- Project workflow: list first, compact context, search/status/sort, and an on-demand create form. WBS defaults to list view, with one shared on-demand add/edit form; hiding it keeps the draft. Detail metrics appear only on the overview tab.
- Work logs: newest-first timeline with text/type filtering; original log titles remain authoritative. One on-demand form contains core fields and an advanced-fields disclosure. Hide/tab changes preserve the current form, and save/delete apply the API response locally without reloading unrelated project forms.
- Goal workflow: select one project, read objective/acceptance criteria and milestones, then explicitly open editing. Drafts and their last fetched baselines live in the root client provider for this tab's lifetime; they are not written to browser storage. Project selection and same-app back/forward retain them. Internal links and the mobile menu ask before leaving dirty goals; browser history is not rewritten or trapped. Native unload warning protects hard reload/close where the browser supports it.
- Goal save boundaries: per-project busy state survives route changes; a saved response cannot overwrite newer typing or another project's draft. An older read completing after a save cannot replace the newer draft baseline. Explicit logout asks before discarding drafts and clears them only after a successful logout response.
- Outcome review: one candidate/review/confirmed list at a time; candidate preparation and record editing open one form in place of the list. Log evidence supports text/date search, selected-only filtering, checkboxes, and full content disclosure. Changes to facts or evidence clear the confirmation checkbox. `resume_ready` remains the stored confirmation flag, not a new lifecycle table.
- Outcome boundaries: candidates remain local suggestions (up to six), not saved outcomes. Review saves may omit evidence; UI confirmation requires a linked log or an existing document reference and explicit user acknowledgement. Existing document IDs are preserved during edits but document contents are not fetched by this screen. Numeric values are never inferred. Drafts survive hiding and same-project tabs, not full route changes or reloads.
- Career result: show one version, defaulting to newest `created_at`, with an older-version selector. Editing an older version does not make it the latest generated result. Version switching and generation ask before discarding edits; failed save/generation retains the draft. Copy while editing uses the current draft. Generation/save responses update local collections without a full project refetch.
- Career boundaries: selection/edit state belongs to the mounted panel; cross-tab/route draft persistence is not implemented. A newly generated version becomes selected only after successful generation. Save and generation lock conflicting panel controls.
- URL state: project list uses `q`, `status`, `sort`; project detail uses `tab`, `view`, `status`, `priority`, `issue`, `sort`. Reload/back restores those conditions. Form drafts remain in memory, not in URL or persistent storage.
- Implemented branch graph components: selected-project branch page with native `프로젝트` select, compact page title, project link, repository loading/error/disconnected states, one `BranchActivityGraph`, compact/full commit range controls, bounded scroll canvas, selected commit detail, refresh button, source timestamp, and branch status disclosure.
- Implemented milestone components: goals page objective/success-criteria forms, milestone rows with WBS count/progress/weight, expandable evidence panel, AI review result card, missing-check list, and acceptance-criteria/pending-WBS/recent-evidence sections.
- Completion review (`/verifications`, 완료 검토) is selected-project first: persisted evidence and validation state load without generating an AI review. Criteria, remaining WBS and linked evidence precede advisory AI output. Milestones are flat rows rather than nested cards. Validation remains an explicit confirmation flow separate from project status and the general progress formula, not a CI/test runner.
- Numeric provenance: commit-derived counted WBS makes progress a reference estimate, excluded from cross-project averages. Missing provenance is unknown, not zero. Project detail exposes counted totals, derived totals and calculation basis. Model confidence is not presented as measured accuracy; task modification time is not labeled completion time.
- Brand asset: `frontend/public/brand/worktrace-mark.svg` is the shared header/login mark and favicon source. The white W trace on green (`#126B5C`) ends at a gold (`#F2BE5C`) point. Keep fixed 34px/40px placements; favicon exports are 16/32/48px ICO and 180px Apple PNG. Do not extend the brand accent into a monochromatic page theme.
- Variants and states: normal, loading, empty, disconnected, partial failure, error, success, editing, saving, copying, stale, batch working, refreshing, disabled, overdue, due-soon, and verified.
- Token/component ownership: global CSS tokens and shared primitives live in `frontend/app/globals.css`; overflow hardening is in `frontend/app/ui-overflow-fixes.css`; branch page layout is scoped to `frontend/app/branches/page.module.css`; branch graph layout is scoped to `BranchActivityGraph.module.css`.
- Alignment contract: standard inputs and command buttons use 40px height; compact table/nav controls use 32px where implemented; panel headers reserve one compact row and wrap actions before overlap.

## Accessibility
- Target standard: WCAG 2.2 AA for core flows.
- Keyboard/focus behavior: global nav, links, buttons, native selects, forms, disclosures, graph canvas, and graph commit nodes expose semantic state or visible focus; branch graph commit nodes are keyboard selectable.
- Contrast/readability: semantic color is paired with text labels such as stale, done, delayed, ready candidate, and disconnected; color is not the only state signal.
- Screen-reader semantics: labeled global nav, page regions, table markup, form labels, `role="status"`, `role="alert"`, `aria-live`, `aria-current`, `aria-expanded`, `aria-pressed`, and `aria-busy` are used where implemented.
- Reduced motion and sensory considerations: transitions are non-essential and disabled under `prefers-reduced-motion`.

## Responsive behavior
- Supported breakpoints/devices: desktop browsers and mobile widths down to 360px, with CSS guardrails down to 320px minimum document width.
- Layout adaptations: dashboard uses two desktop columns and one mobile column; summary metrics use four columns and two at 640px and below. Project and WBS filters keep status/sort pairs side by side on mobile. Other dense tables keep horizontal scroll.
- Variable content: long titles and evidence strings use `overflow-wrap`; table wrappers and the full-history graph use bounded overflow. The summary graph fits node spacing to available width without scaling label fonts. Shared HEAD refs use one representative label plus a count; labels are measured and packed separately from history lanes. Summary height follows content rather than clipping nodes below stacked names.
- Mobile planning: milestone rows and verification actions collapse to single-column full-width controls; count badges and pills can wrap at narrow widths.
- Narrow header behavior: the logo remains the dashboard route; a native route select replaces the horizontally scrolling desktop links at 760px and below.
- Touch/hover differences: actions remain visible without hover; hover polish is optional, while focus and disabled states are explicit.

## Interaction states
- Loading: short Korean status text near the affected surface; branch page separates project loading from selected repository loading.
- Empty: one concise state such as `표시할 프로젝트가 없습니다.`, `연결된 GitHub 저장소가 없습니다.`, or `표시할 브랜치가 없습니다.`.
- Disconnected: repository absence is distinct from repository fetch failure on the branch page and graph component.
- Error: alert surfaces retain page context and provide retry where the current implementation supports it.
- Success: success alerts use `role="status"` or `aria-live` near the completed action, including report copy and validation changes.
- Disabled: reserved for in-flight work, unavailable selected context, already-current batch review, or protected validation paths.
- Offline/slow network: duplicate submits are prevented with disabled buttons; abort/cancel guards prevent stale selected-project repository responses from rendering.

## Content voice
- Tone: concise Korean operational language.
- Terminology: use 프로젝트, WBS, 이슈, 커밋 근거, Evidence, 업무 로그, 성취 기준, 검증 완료, 브랜치 그래프, 인사이트, 리포트, 성과, and 경력 자산 consistently.
- Microcopy rules: command labels describe the result; omit English kickers when not necessary; branch and verification pages should not duplicate project titles, progress summaries, or decorative eyebrow text when the component already provides context.

## Implementation constraints
- Framework/styling system: Next.js App Router, React, TypeScript, repo-local CSS modules/global CSS, and no new dependencies unless explicitly justified.
- Design-token constraints: extend current CSS variables and shared primitives; do not create a second theme layer or conflicting token names.
- Performance constraints: avoid extra per-item API waterfalls on heavy visual pages; branch graph must load projects first and then only the selected project repository/branch activity.
- Compatibility constraints: preserve backend owner/token service boundaries, signed single-user session behavior outside unconfigured local development, and Korean UX.
- Progress constraints: only `counts_toward_progress` WBS is counted. A nonempty set with every counted WBS assigned to a milestone uses the weighted milestone average; any unassigned counted WBS selects the overall WBS ratio. No counted WBS means `unscoped`, displayed as `산정 전`.
- AI constraints: AI review and analyst outputs are advisory; user confirmation remains the only path that marks milestone validation complete.
- Test/screenshot expectations: keep frontend contract tests current with shipped routes; run targeted tests plus typecheck/lint for doc-adjacent UI changes, and use desktop/mobile screenshots for visual implementation changes.

## Open questions
- [ ] Define the next single-user access-control and operational hardening checklist for the current worktrace.cloud deployment; owner: product/ops; impact: auth policy, monitoring, backup, and incident recovery.
- [ ] Decide the allowed sensitivity of future uploaded documents; owner: product; impact: retention, encryption, and AI data boundaries.
- [ ] Decide when document ingestion becomes the next vertical slice; owner: product; impact: navigation and schema expansion.
- Resolved: `dashboard-topbar` remains the shared compact page heading but no longer has a card border, background, or shadow. Dashboard sections use unframed bands; legacy tool panels are not claimed to be fully migrated.
