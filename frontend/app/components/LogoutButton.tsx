"use client";

export function LogoutButton() {
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  return <button className="header-logout" type="button" onClick={() => void logout()}>로그아웃</button>;
}
