"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppLogo } from "./AppLogo";
import { LogoutButton } from "./LogoutButton";

export function AppHeader({ authEnabled }: { authEnabled: boolean }) {
  const pathname = usePathname();
  if (pathname === "/login") return null;

  const isProjects = pathname.startsWith("/projects");
  const isReports = pathname.startsWith("/reports");

  return (
    <header className="app-header" aria-label="전역 이동">
      <div className="app-header-inner">
        <AppLogo />
        <nav className="app-nav" aria-label="주요 메뉴">
          <Link aria-current={pathname === "/" ? "page" : undefined} href="/">대시보드</Link>
          <Link href="/#quick-capture">기록</Link>
          <Link aria-current={isProjects ? "page" : undefined} href="/projects">프로젝트</Link>
          <Link aria-current={isReports ? "page" : undefined} href="/reports">리포트</Link>
          {authEnabled ? <LogoutButton /> : null}
        </nav>
      </div>
    </header>
  );
}
