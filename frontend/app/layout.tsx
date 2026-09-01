import type { Metadata } from "next";
import Link from "next/link";
import { AppLogo } from "./components/AppLogo";
import "./globals.css";

export const metadata: Metadata = {
  title: "work-support",
  description: "Personal work automation and career assetization platform"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <div className="app-frame">
          <header className="app-header" aria-label="전역 이동">
            <div className="app-header-inner">
              <AppLogo />
              <nav className="app-nav" aria-label="주요 메뉴">
                <Link href="/">대시보드</Link>
                <Link href="/#quick-capture">기록</Link>
                <Link href="/projects">프로젝트</Link>
                <Link href="/reports">리포트</Link>
              </nav>
            </div>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
