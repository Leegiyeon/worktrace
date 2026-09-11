import { NextRequest } from "next/server";

import { encodePathSegment, proxyBackend } from "../../../backend";

type RouteContext = { params: Promise<{ projectId: string }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { projectId } = await context.params;
  return proxyBackend(request, `/projects/${encodePathSegment(projectId)}/commits`);
}
