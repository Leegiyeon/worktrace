import type { Metadata } from "next";
import { AppHeader } from "./components/AppHeader";
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
          <AppHeader authEnabled={Boolean(process.env.WORK_SUPPORT_PASSWORD_HASH && process.env.WORK_SUPPORT_SESSION_SECRET)} />
          {children}
        </div>
      </body>
    </html>
  );
}
