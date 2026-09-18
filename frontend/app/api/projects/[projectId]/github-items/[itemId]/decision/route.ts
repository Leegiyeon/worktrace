import { NextRequest } from "next/server";
import { encodePathSegment, proxyBackend } from "../../../../../backend";

type RouteContext = { params: Promise<{ projectId: string; itemId: string }> };

export async function POST(request: NextRequest, context: RouteContext) {
  const { projectId, itemId } = await context.params;
  return proxyBackend(request, `/projects/${encodePathSegment(projectId)}/github-items/${encodePathSegment(itemId)}/decision`);
}
