// Liveness of the web app plus reachability of the API (used by the Docker health check and smoke tests).
import { NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/server/session";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  let api: "ok" | "unreachable" = "unreachable";
  try {
    const res = await fetch(`${apiBaseUrl()}/health`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    api = res.ok ? "ok" : "unreachable";
  } catch {
    api = "unreachable";
  }
  return NextResponse.json({ data: { status: "ok", api }, error: null }, { headers: { "Cache-Control": "no-store" } });
}
