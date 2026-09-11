import { createHmac, scryptSync, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "worktrace_session";
export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 12;

type SessionPayload = {
  exp: number;
  sub: string;
};

function sessionSecret() {
  return process.env.WORKTRACE_SESSION_SECRET ?? process.env.WORK_SUPPORT_SESSION_SECRET ?? "";
}

function signature(payload: string) {
  return createHmac("sha256", sessionSecret()).update(payload).digest("base64url");
}

export function authIsConfigured() {
  return Boolean((process.env.WORKTRACE_PASSWORD_HASH ?? process.env.WORK_SUPPORT_PASSWORD_HASH) && sessionSecret().length >= 32);
}

export function verifyPassword(password: string) {
  const encoded = process.env.WORKTRACE_PASSWORD_HASH ?? process.env.WORK_SUPPORT_PASSWORD_HASH ?? "";
  const [algorithm, salt, expectedHex] = encoded.split("$");
  if (algorithm !== "scrypt" || !/^[a-f0-9]{32}$/i.test(salt) || !/^[a-f0-9]{128}$/i.test(expectedHex)) {
    return false;
  }

  const expected = Buffer.from(expectedHex, "hex");
  const actual = scryptSync(password, salt, expected.length);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

export function createSessionToken() {
  const payload: SessionPayload = {
    sub: process.env.WORKTRACE_OWNER_ID ?? process.env.WORK_SUPPORT_OWNER_ID ?? "local-owner",
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_SECONDS
  };
  const encoded = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${encoded}.${signature(encoded)}`;
}
