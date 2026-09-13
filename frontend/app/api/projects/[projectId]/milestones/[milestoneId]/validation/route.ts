import { NextRequest } from "next/server";

import { encodePathSegment, proxyBackend } from "../../../../../backend";

type RouteContext = {
  params: Promise<{ projectId: string; milestoneId: string }>;
};

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { projectId, milestoneId } = await context.params;
  return proxyBackend(request, `/projects/${encodePathSegment(projectId)}/milestones/${encodePathSegment(milestoneId)}/validation`);
}
