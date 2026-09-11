import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "worktrace_session";

function base64UrlToBytes(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function hasValidSession(request: NextRequest) {
  const secret = process.env.WORKTRACE_SESSION_SECRET ?? process.env.WORK_SUPPORT_SESSION_SECRET ?? "";
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (secret.length < 32 || !token) return false;

  const [payload, suppliedSignature] = token.split(".");
  if (!payload || !suppliedSignature) return false;

  try {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { hash: "SHA-256", name: "HMAC" },
      false,
      ["verify"]
    );
    const valid = await crypto.subtle.verify(
      "HMAC",
      key,
      base64UrlToBytes(suppliedSignature),
      new TextEncoder().encode(payload)
    );
    if (!valid) return false;
    const parsed = JSON.parse(new TextDecoder().decode(base64UrlToBytes(payload))) as { exp?: number };
    return typeof parsed.exp === "number" && parsed.exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

export async function proxy(request: NextRequest) {
  const isProduction = process.env.NODE_ENV === "production";
  const passwordHash = process.env.WORKTRACE_PASSWORD_HASH ?? process.env.WORK_SUPPORT_PASSWORD_HASH;
  const sessionSecret = process.env.WORKTRACE_SESSION_SECRET ?? process.env.WORK_SUPPORT_SESSION_SECRET;
  const authConfigured = Boolean(passwordHash && (sessionSecret?.length ?? 0) >= 32);
  if (!isProduction && !authConfigured) return NextResponse.next();

  if (await hasValidSession(request)) return NextResponse.next();

  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ message: "로그인이 필요합니다." }, { status: 401 });
  }

  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|login|api/auth).*)"]
};
