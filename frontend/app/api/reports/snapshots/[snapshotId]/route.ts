import { NextRequest } from "next/server";

import { encodePathSegment, proxyBackend } from "../../../backend";

type RouteContext = {
  params: Promise<{ snapshotId: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { snapshotId } = await context.params;
  return proxyBackend(request, `/reports/snapshots/${encodePathSegment(snapshotId)}`);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { snapshotId } = await context.params;
  return proxyBackend(request, `/reports/snapshots/${encodePathSegment(snapshotId)}`);
}
