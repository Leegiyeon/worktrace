"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppLogo } from "./AppLogo";
import { LogoutButton } from "./LogoutButton";

export function AppHeader({ authEnabled }: { authEnabled: boolean }) {
  const pathname = usePathname();
  if (pathname === "/login") return null;

  const isProjects = pathname.startsWith("/projects");
  const isGoals = pathname.startsWith("/goals");
  const isVerifications = pathname.startsWith("/verifications");
  const isBranches = pathname.startsWith("/branches");
  const isInsights = pathname.startsWith("/insights");
  const isReports = pathname.startsWith("/reports");

  return (
    <header className="app-header" aria-label="전역 이동">
      <div className="app-header-inner">
        <AppLogo />
        <div className="app-header-actions">
          <nav className="app-nav" aria-label="주요 메뉴">
            <Link aria-current={isProjects ? "page" : undefined} href="/projects">프로젝트</Link>
            <Link aria-current={isGoals ? "page" : undefined} href="/goals">목표·마일스톤</Link>
            <Link aria-current={isVerifications ? "page" : undefined} href="/verifications">검증센터</Link>
            <Link aria-current={isBranches ? "page" : undefined} href="/branches">브랜치 그래프</Link>
            <Link aria-current={isInsights ? "page" : undefined} href="/insights">인사이트</Link>
            <Link aria-current={isReports ? "page" : undefined} href="/reports">리포트</Link>
          </nav>
          {authEnabled ? <LogoutButton /> : null}
        </div>
      </div>
    </header>
  );
}
