import type { Metadata } from "next";
import { AppHeader } from "./components/AppHeader";
import { GoalDraftProvider } from "./components/GoalDraftProvider";
import "./globals.css";
import "./ui-overflow-fixes.css";

export const metadata: Metadata = {
  title: "worktrace",
  description: "Personal work automation and career assetization platform",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "16x16 32x32 48x48" },
      { url: "/brand/worktrace-mark.svg", type: "image/svg+xml", sizes: "any" }
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  }
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
