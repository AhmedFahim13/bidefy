import { NextRequest, NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

// Browser calls go through the site origin because some networks block *.workers.dev.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TIMEOUT_MS = 15_000;

async function forward(req: NextRequest, path: string[]): Promise<NextResponse> {
  const url = new URL(`${API_BASE}/api/${path.join("/")}`);
  url.search = req.nextUrl.search;
  const headers: Record<string, string> = { accept: "application/json" };
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  const admin = req.headers.get("x-admin-token");
  if (admin) headers["x-admin-token"] = admin;
  const ip = req.headers.get("x-forwarded-for");
  if (ip) headers["x-forwarded-for"] = ip;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();
    const upstream = await fetch(url, { method: req.method, headers, body, signal: controller.signal, cache: "no-store" });
    const text = await upstream.text();
    return new NextResponse(text, { status: upstream.status, headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" } });
  } catch {
    return NextResponse.json({ error: "the data service did not respond" }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
}

type Ctx = { params: Promise<{ path: string[] }> };
export async function GET(req: NextRequest, ctx: Ctx) { return forward(req, (await ctx.params).path); }
export async function POST(req: NextRequest, ctx: Ctx) { return forward(req, (await ctx.params).path); }
export async function DELETE(req: NextRequest, ctx: Ctx) { return forward(req, (await ctx.params).path); }
