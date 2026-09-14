import type { Metadata } from "next";
import { AppHeader } from "./components/AppHeader";
import { GoalDraftProvider } from "./components/GoalDraftProvider";
import "./globals.css";
import "./ui-overflow-fixes.css";

export const metadata: Metadata = {
  title: "worktrace",
  description: "Personal work automation and career assetization platform"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <GoalDraftProvider>
        <div className="app-frame">
          <AppHeader authEnabled={Boolean(
            (process.env.WORKTRACE_PASSWORD_HASH ?? process.env.WORK_SUPPORT_PASSWORD_HASH)
            && (process.env.WORKTRACE_SESSION_SECRET ?? process.env.WORK_SUPPORT_SESSION_SECRET)
          )} />
          {children}
        </div>
        </GoalDraftProvider>
      </body>
    </html>
  );
}
