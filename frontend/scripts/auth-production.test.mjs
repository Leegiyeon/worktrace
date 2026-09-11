import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("session cookie is signed, http-only, strict, and production-secure", () => {
  const session = read("app/auth/session.ts");
  const login = read("app/api/auth/login/route.ts");

  assert.match(session, /createHmac\("sha256"/);
  assert.match(session, /scryptSync/);
  assert.match(session, /\{128\}/);
  assert.match(login, /httpOnly:\s*true/);
  assert.match(login, /sameSite:\s*"strict"/);
  assert.match(login, /secure:\s*process\.env\.NODE_ENV === "production"/);
});

test("login applies bounded failure attempts and never accepts an unconfigured secret", () => {
  const login = read("app/api/auth/login/route.ts");

  assert.match(login, /MAX_ATTEMPTS = 5/);
  assert.match(login, /status:\s*429/);
  assert.match(login, /authIsConfigured\(\)/);
  assert.match(login, /status:\s*503/);
});

test("request proxy protects pages and APIs while preserving local setup", () => {
  const proxy = read("proxy.ts");

  assert.match(proxy, /hasValidSession/);
  assert.match(proxy, /request\.nextUrl\.pathname\.startsWith\("\/api\/"\)/);
  assert.match(proxy, /status:\s*401/);
  assert.match(proxy, /NextResponse\.redirect\(new URL\("\/login"/);
  assert.match(proxy, /!isProduction && !authConfigured/);
});

test("production compose runs release commands without source mounts or public internal ports", () => {
  const compose = read("../docker-compose.prod.yml");
  const frontendDockerfile = read("Dockerfile");
  const deployScript = read("../scripts/deploy_oracle.sh");

  assert.match(compose, /APP_ENV:\s*production/);
  assert.match(compose, /WORKTRACE_PASSWORD_HASH/);
  assert.match(compose, /WORKTRACE_SESSION_SECRET/);
  assert.match(deployScript, /WORK_SUPPORT_PASSWORD_HASH=.*WORKTRACE_PASSWORD_HASH/);
  assert.match(deployScript, /WORK_SUPPORT_SESSION_SECRET=.*WORKTRACE_SESSION_SECRET/);
  assert.match(compose, /GITHUB_WEBHOOK_SECRET/);
  assert.doesNotMatch(compose, /--reload|npm run dev|\.\/frontend\/app:\/app\/app/);
  assert.doesNotMatch(compose, /5432:5432|8000:8000|127\.0\.0\.1:\$\{FRONTEND_PORT/);
  assert.match(compose, /APP_DOMAIN:\s*\$\{APP_DOMAIN:\?Set APP_DOMAIN\}/);
  assert.match(compose, /"80:80"/);
  assert.match(compose, /"443:443"/);
  assert.match(compose, /\.\/Caddyfile:\/etc\/caddy\/Caddyfile:ro/);
  assert.match(compose, /health\/ready/);
  assert.match(frontendDockerfile, /npm run build/);
  assert.match(frontendDockerfile, /npm", "run", "start/);
  assert.match(frontendDockerfile, /USER nextjs/);
});

test("Caddy terminates HTTPS and applies baseline response controls", () => {
  const caddyfile = read("../Caddyfile");

  assert.match(caddyfile, /\{\$APP_DOMAIN\}/);
  assert.match(caddyfile, /reverse_proxy frontend:3000/);
  assert.match(caddyfile, /handle \/webhooks\/github[\s\S]*reverse_proxy backend:8000/);
  assert.match(caddyfile, /Strict-Transport-Security/);
  assert.match(caddyfile, /X-Content-Type-Options "nosniff"/);
  assert.match(caddyfile, /max_size 10MB/);
});

test("password hashing tool reads a hidden terminal value instead of a process argument", () => {
  const generator = read("../scripts/generate_password_hash.mjs");

  assert.match(generator, /stty", \["-echo"\]/);
  assert.match(generator, /process\.stdin/);
  assert.doesNotMatch(generator, /process\.argv\[2\]/);
});
