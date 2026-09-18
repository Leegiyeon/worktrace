import { NextRequest } from "next/server";
import { encodePathSegment, proxyBackend } from "../../../backend";

type Context = { params: Promise<{ projectId: string }> };

export async function GET(request: NextRequest, context: Context) {
  const { projectId } = await context.params;
  return proxyBackend(request, `/projects/${encodePathSegment(projectId)}/lifecycle`);
}

export async function POST(request: NextRequest, context: Context) {
  const { projectId } = await context.params;
  return proxyBackend(request, `/projects/${encodePathSegment(projectId)}/lifecycle`);
}
