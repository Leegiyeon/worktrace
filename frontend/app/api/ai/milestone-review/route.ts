import { NextRequest } from "next/server";

import { proxyBackend } from "../../backend";

export async function POST(request: NextRequest) {
  return proxyBackend(request, "/ai/milestone-review");
}
