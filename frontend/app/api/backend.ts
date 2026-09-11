import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.WORKTRACE_BACKEND_URL ?? process.env.WORK_SUPPORT_BACKEND_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const OWNER_ID = process.env.WORKTRACE_OWNER_ID ?? process.env.WORK_SUPPORT_OWNER_ID ?? process.env.NEXT_PUBLIC_WORKTRACE_OWNER_ID ?? process.env.NEXT_PUBLIC_WORK_SUPPORT_OWNER_ID ?? "local-owner";
const REPORT_ACCESS_TOKEN = process.env.WORKTRACE_REPORT_TOKEN ?? process.env.WORK_SUPPORT_REPORT_TOKEN ?? process.env.REPORT_ACCESS_TOKEN ?? "dev-only-report-token";

export function encodePathSegment(segment: string) {
  return encodeURIComponent(segment);
}

export async function proxyBackend(request: NextRequest, path: string) {
  const url = new URL(`${BACKEND_URL}${path}`);
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value));

  let response: Response;
  try {
    response = await fetch(url, {
      method: request.method,
      headers: {
        "Content-Type": request.headers.get("Content-Type") ?? "application/json",
        "X-Worktrace-Owner-Id": OWNER_ID,
        "X-Worktrace-Report-Token": REPORT_ACCESS_TOKEN
      },
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store"
    });
  } catch {
    return NextResponse.json(
      {
        detail: {
          code: "BACKEND_UNAVAILABLE",
          message: "백엔드에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
        }
      },
      { status: 502 }
    );
  }

  const body = request.method === "HEAD" || response.status === 204 ? null : await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json"
    }
  });
}
