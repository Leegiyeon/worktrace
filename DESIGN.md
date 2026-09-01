# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-09-01
- Primary product surfaces: dashboard, project list, project detail, reports
- Evidence reviewed: `AGENTS.md`, `docs/DESIGN_SYSTEM.md`, `README.md`, frontend routes, shared CSS, API contracts, and current UI tests

## Brand
- Personality: quiet, precise, work-focused, and trustworthy
- Trust signals: evidence-linked outcomes, explicit status, owner-scoped data, and no fabricated metrics
- Avoid: marketing copy, decorative hero layouts, disabled feature promises, and card-only composition

## Product goals
- Goals: capture daily work quickly, expose the next action, preserve project evidence, and turn confirmed outcomes into reusable career material
- Non-goals: multi-user SaaS, public sharing, OCR, document RAG, and advanced WBS import in the first usable service
- Success signals: a user can record work, update tasks, confirm outcomes, edit career text, and generate a weekly report without leaving the core workflow

## Personas and jobs
- Primary personas: one knowledge worker managing personal project evidence and career history
- User jobs: decide what needs attention, record completed work, preserve decisions/blockers, confirm measurable outcomes, and reuse career statements
- Key contexts of use: daily desktop review, quick mobile capture, weekly reporting, and periodic resume preparation

## Information architecture
- Primary navigation: dashboard, projects, reports
- Core routes/screens: `/`, `/projects`, `/projects/[projectId]`, `/reports`
- Content hierarchy: urgent work and quick capture first; project status and evidence second; reports and career reuse after records exist

## Design principles
- Action before summary: overdue, due-soon, and next-action records precede aggregate charts
- Evidence before generation: career content follows work logs and confirmed outcomes
- Progressive disclosure: common fields stay visible; secondary evidence fields use compact disclosure controls
- Honest scope: unavailable features do not appear as active navigation or disabled promises
- Tradeoffs: desktop keeps dense tables and boards; mobile prioritizes capture, status, and horizontal overflow over reduced data fidelity

## Visual language
- Color: navy for product identity, neutral surfaces for density, semantic green/amber/red only for state
- Typography: system sans-serif, compact headings, no viewport-scaled type, letter spacing `0`
- Spacing/layout rhythm: 8px-based compact rhythm, constrained wide content, stable grid tracks
- Shape/radius/elevation: 6-8px radius, restrained borders and shadows, no floating section cards
- Motion: minimal state transitions; respect reduced-motion preferences
- Imagery/iconography: no decorative imagery; familiar text commands remain acceptable until an icon library is part of the existing stack

## Components
- Existing components to reuse: metric rows, dense lists, data tables, progress bars, badges, forms, tab navigation, and alerts
- New/changed components: attention queue, project quick actions, editable career asset workspace
- Variants and states: normal, overdue, due-soon, loading, empty, error, success, editing, saving, and copied
- Token/component ownership: CSS tokens and shared primitives remain in `frontend/app/globals.css`; domain interactions stay with their route/component

## Accessibility
- Target standard: WCAG 2.2 AA for core flows
- Keyboard/focus behavior: all tabs, disclosures, links, and form actions expose visible focus and semantic selection state
- Contrast/readability: semantic colors must retain readable text and not be the only state signal
- Screen-reader semantics: labeled navigation, regions, tables, forms, status alerts, and progress values
- Reduced motion and sensory considerations: no essential information depends on animation

## Responsive behavior
- Supported breakpoints/devices: current desktop browsers and mobile widths down to 360px
- Layout adaptations: dashboard grids collapse to one column; dense tables keep horizontal scrolling; action bars wrap without overlap
- Touch/hover differences: actions remain visible and usable without hover; controls retain at least the existing control height

## Interaction states
- Loading: preserve layout and use short status text
- Empty: one concise state plus the relevant action
- Error: retain user input and show a concrete recovery message
- Success: show a short status close to the action that completed
- Disabled: only for in-flight actions, not for unavailable product promises
- Offline/slow network: prevent duplicate submits and preserve the editable form while requests are pending

## Content voice
- Tone: concise Korean operational language
- Terminology: use 프로젝트, 업무, 업무 로그, 성과, 근거, 경력 자산 consistently
- Microcopy rules: command labels describe the result; omit English kickers, repeated subtitles, and explanatory filler

## Implementation constraints
- Framework/styling system: Next.js App Router, React, TypeScript, and repo-local CSS without new dependencies
- Design-token constraints: extend existing tokens and semantic classes; do not create a second theme layer
- Performance constraints: avoid additional per-item API waterfalls; keep dashboard requests bounded by the current project set
- Compatibility constraints: preserve the local owner/token proxy boundary and Korean UX
- Test/screenshot expectations: API proxy tests, frontend contract tests, typecheck, lint, production build, and desktop/mobile browser screenshots for changed flows

## Open questions
- [ ] Decide whether the first deployment remains localhost-only or moves behind a personal VPN; owner: product; impact: authentication and storage work
- [ ] Decide the allowed sensitivity of future uploaded documents; owner: product; impact: retention, encryption, and AI data boundaries
- [ ] Decide when document ingestion becomes the next vertical slice; owner: product; impact: navigation and schema expansion
