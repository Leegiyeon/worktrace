import Link from "next/link";

export function AppLogo() {
  return (
    <Link className="app-logo" href="/" aria-label="worktrace 대시보드로 이동">
      <span className="app-logo-mark" aria-hidden="true">
        <svg viewBox="0 0 44 44" role="img" focusable="false">
          <rect className="mark-bg" x="3" y="3" width="38" height="38" rx="12" />
          <path className="mark-grid" d="M14 14h8M14 34h16M30 28h4" />
          <path className="mark-check" d="M13 23.5l5 5L31 15" />
        </svg>
      </span>
      <span className="app-logo-text">
        <strong>worktrace</strong>
        <small>WORK OS</small>
      </span>
    </Link>
  );
}
