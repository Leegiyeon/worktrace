"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useGoalDrafts } from "./GoalDraftProvider";

export function LogoutButton() {
  const router = useRouter();
  const { confirmNavigation, clearDrafts } = useGoalDrafts();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    if (!confirmNavigation(true)) return;
    setIsLoggingOut(true);
    setError("");
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("로그아웃하지 못했습니다.");
      clearDrafts();
      router.replace("/login");
      router.refresh();
    } catch {
      setError("로그아웃 실패. 다시 시도하세요.");
    } finally {
      setIsLoggingOut(false);
    }
  }

  return <><button className="header-logout" disabled={isLoggingOut} type="button" onClick={() => void logout()}>{isLoggingOut ? "로그아웃 중" : "로그아웃"}</button>{error ? <span role="alert">{error}</span> : null}</>;
}
