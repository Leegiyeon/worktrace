"use client";

import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password })
      });
      const body = (await response.json().catch(() => null)) as { message?: string } | null;
      if (!response.ok) throw new Error(body?.message ?? "로그인하지 못했습니다.");
      window.location.assign("/");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "로그인하지 못했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="panel login-panel" aria-labelledby="login-title">
        <div>
          <span className="status-pill">개인 업무공간</span>
          <h1 id="login-title">worktrace</h1>
        </div>
        <form className="stacked-form" onSubmit={handleSubmit}>
          <label>
            비밀번호
            <input
              autoComplete="current-password"
              autoFocus
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          <button disabled={isSubmitting} type="submit">{isSubmitting ? "확인 중" : "로그인"}</button>
        </form>
        {error ? <div className="alert error" role="alert">{error}</div> : null}
      </section>
    </main>
  );
}
