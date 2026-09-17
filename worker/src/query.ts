export type TenderFilters = { q: string; status: string; ministry: string; district: string; category: string; page: number; size: number };
export type Query = { sql: string; params: (string | number)[] };

const MAX_SIZE = 100;

/** Construction and its types. Most construction tenders state no type, so they are plain "construction". */
export const CONSTRUCTION_TYPES = ["construction", "roads_bridges", "buildings_civil", "water_sanitation"];

/** Asking for construction finds every construction tender; asking for a type finds only that type. */
export function categoryMatches(have: string | null | undefined, want: string): boolean {
  if (want === "construction") return CONSTRUCTION_TYPES.includes(have ?? "");
  return (have ?? "") === want;
}

export function parseTenderFilters(sp: URLSearchParams): TenderFilters {
  const page = Math.max(1, Number.parseInt(sp.get("page") ?? "1", 10) || 1);
  const size = Math.min(MAX_SIZE, Math.max(1, Number.parseInt(sp.get("size") ?? "25", 10) || 25));
  return {
    q: (sp.get("q") ?? "").trim(),
    status: (sp.get("status") ?? "Live").trim() || "Live",
    ministry: (sp.get("ministry") ?? "").trim(),
    district: (sp.get("district") ?? "").trim(),
    category: (sp.get("category") ?? "").trim(),
    page,
    size,
  };
}

export function tenderListQuery(f: TenderFilters): Query {
  const where: string[] = [];
  const params: (string | number)[] = [];
  if (f.status !== "all") { where.push("status = ?"); params.push(f.status); }
  if (f.q) { where.push("title LIKE ?"); params.push(`%${f.q}%`); }
  if (f.ministry) { where.push("ministry = ?"); params.push(f.ministry); }
  if (f.category === "construction") {
    where.push(`category IN (${CONSTRUCTION_TYPES.map(() => "?").join(", ")})`);
    params.push(...CONSTRUCTION_TYPES);
  } else if (f.category) {
    where.push("category = ?");
    params.push(f.category);
  }
  const sql =
    "SELECT tender_id, reference, status, nature, title, ministry, organization, procuring_entity, pe_id, method, published_at, closing_at, category, category_confidence " +
    "FROM tenders" + (where.length ? " WHERE " + where.join(" AND ") : "") +
    " ORDER BY published_at DESC LIMIT ? OFFSET ?";
  params.push(f.size, (f.page - 1) * f.size);
  return { sql, params };
}

export function tenderByIdQuery(id: string): Query {
  return {
    sql:
      "SELECT t.*, c.awardee, c.bidder_id, c.value_crore, c.signed_on, c.district " +
      "FROM tenders t LEFT JOIN contracts c ON c.tender_id = t.tender_id WHERE t.tender_id = ?",
    params: [id],
  };
}

export function predictionQuery(id: string): Query {
  return { sql: "SELECT q10_lakh, q50_lakh, q90_lakh, deferred, basis, model_version FROM predictions WHERE tender_id = ?", params: [id] };
}

export function bidderQuery(id: string): Query {
  return { sql: "SELECT * FROM bidders WHERE bidder_id = ?", params: [id] };
}

export function peQuery(id: string): Query {
  return { sql: "SELECT * FROM procuring_entities WHERE pe_id = ?", params: [id] };
}

/** Parse a JSON aggregate column; never throws, never returns anything but an array. */
export function parseJsonList(value: unknown): unknown[] {
  if (typeof value !== "string" || !value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Parse a JSON aggregate column holding an object; never throws. */
export function parseJsonObject(value: unknown): Record<string, unknown> {
  if (typeof value !== "string" || !value) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}
