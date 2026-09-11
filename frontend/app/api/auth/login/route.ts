import { NextRequest, NextResponse } from "next/server";
import {
  authIsConfigured,
  createSessionToken,
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  verifyPassword
} from "../../../auth/session";

export const runtime = "nodejs";

const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 5;
const attempts = new Map<string, { count: number; resetAt: number }>();

function clientKey(request: NextRequest) {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
}

function isRateLimited(key: string) {
  const now = Date.now();
  const current = attempts.get(key);
  if (!current || current.resetAt <= now) {
    attempts.delete(key);
    return false;
  }
  return current.count >= MAX_ATTEMPTS;
}

function recordFailure(key: string) {
  if (attempts.size >= 10_000) {
    const now = Date.now();
    for (const [candidate, value] of attempts) {
      if (value.resetAt <= now) attempts.delete(candidate);
    }
    if (attempts.size >= 10_000) attempts.delete(attempts.keys().next().value ?? "");
  }
  const current = attempts.get(key) ?? { count: 0, resetAt: Date.now() + WINDOW_MS };
  attempts.set(key, { ...current, count: current.count + 1 });
}

export async function POST(request: NextRequest) {
  if (!authIsConfigured()) {
    return NextResponse.json({ message: "로그인 설정이 완료되지 않았습니다." }, { status: 503 });
  }

  const key = clientKey(request);
  if (isRateLimited(key)) {
    return NextResponse.json({ message: "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요." }, { status: 429 });
  }

  const body = (await request.json().catch(() => null)) as { password?: unknown } | null;
  const password = typeof body?.password === "string" ? body.password : "";
  if (!password || !verifyPassword(password)) {
    recordFailure(key);
    return NextResponse.json({ message: "비밀번호가 올바르지 않습니다." }, { status: 401 });
  }

  attempts.delete(key);

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, createSessionToken(), {
    httpOnly: true,
    maxAge: SESSION_MAX_AGE_SECONDS,
    path: "/",
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production"
  });
  return response;
}
