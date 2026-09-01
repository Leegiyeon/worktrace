import { NextRequest } from "next/server";

import { encodePathSegment, proxyBackend } from "../../../../backend";

type RouteContext = {
  params: Promise<{ projectId: string; careerAssetId: string }>;
};

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { projectId, careerAssetId } = await context.params;
  return proxyBackend(
    request,
    `/projects/${encodePathSegment(projectId)}/career-assets/${encodePathSegment(careerAssetId)}`
  );
}
