import { NextRequest } from "next/server";

import { encodePathSegment, proxyBackend } from "../../../../../backend";

type RouteContext = { params: Promise<{ projectId: string; deliveryId: string }> };

export async function POST(request: NextRequest, context: RouteContext) {
  const { projectId, deliveryId } = await context.params;
  return proxyBackend(
    request,
    `/projects/${encodePathSegment(projectId)}/github-deliveries/${encodePathSegment(deliveryId)}/reprocess`
  );
}
