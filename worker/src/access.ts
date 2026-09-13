export const VALUE_BANDS = ["under_10_lakh", "10_lakh_to_1_crore", "1_to_10_crore", "over_10_crore"] as const;
export type ValueBand = (typeof VALUE_BANDS)[number];
export type AccessRequest = { name: string; organisation: string; role: string; bids_on: string; value_band: ValueBand; contact: string; note: string };
export type AccessResult = { ok: true; value: AccessRequest } | { ok: false; error: string };

function str(v: unknown, max: number): string {
  return typeof v === "string" ? v.trim().slice(0, max) : "";
}

export function validateAccessRequest(body: unknown): AccessResult {
  const b = (body ?? {}) as Record<string, unknown>;
  if (str(b.website, 10)) return { ok: false, error: "rejected" };            // honeypot
  const name = str(b.name, 80);
  const organisation = str(b.organisation, 120);
  const bids_on = str(b.bids_on, 200);
  const value_band = str(b.value_band, 40) as ValueBand;
  const contact = str(b.contact, 120);
  if (name.length < 2) return { ok: false, error: "name is required" };
  if (organisation.length < 2) return { ok: false, error: "organisation is required" };
  if (bids_on.length < 2) return { ok: false, error: "tell us what you bid on" };
  if (!VALUE_BANDS.includes(value_band)) return { ok: false, error: "pick a value band" };
  if (contact && contact.length < 5) return { ok: false, error: "contact looks too short" };
  return { ok: true, value: { name, organisation, role: str(b.role, 80), bids_on, value_band, contact, note: str(b.note, 500) } };
}

export async function hashIp(ip: string): Promise<string> {
  const data = new TextEncoder().encode("bidefy:" + ip);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (x) => x.toString(16).padStart(2, "0")).join("").slice(0, 32);
}
