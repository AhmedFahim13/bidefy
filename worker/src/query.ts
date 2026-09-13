export type TenderFilters = { q: string; status: string; ministry: string; district: string; page: number; size: number };
export type Query = { sql: string; params: (string | number)[] };

const MAX_SIZE = 100;

export function parseTenderFilters(sp: URLSearchParams): TenderFilters {
  const page = Math.max(1, Number.parseInt(sp.get("page") ?? "1", 10) || 1);
  const size = Math.min(MAX_SIZE, Math.max(1, Number.parseInt(sp.get("size") ?? "25", 10) || 25));
  return {
    q: (sp.get("q") ?? "").trim(),
    status: (sp.get("status") ?? "Live").trim() || "Live",
    ministry: (sp.get("ministry") ?? "").trim(),
    district: (sp.get("district") ?? "").trim(),
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
  const sql =
    "SELECT tender_id, reference, status, nature, title, ministry, organization, procuring_entity, pe_id, method, published_at, closing_at " +
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

export function similarAwardsQuery(peId: string): Query {
  return {
    sql: "SELECT tender_id, title, awardee, bidder_id, value_crore, signed_on FROM contracts WHERE pe_id = ? ORDER BY signed_on DESC LIMIT 10",
    params: [peId],
  };
}

export function bidderQuery(id: string): Query {
  return { sql: "SELECT * FROM bidders WHERE bidder_id = ?", params: [id] };
}

export function bidderAwardsQuery(id: string): Query {
  return {
    sql: "SELECT tender_id, title, procuring_entity, pe_id, district, value_crore, signed_on FROM contracts WHERE bidder_id = ? ORDER BY signed_on DESC LIMIT 50",
    params: [id],
  };
}

export function peQuery(id: string): Query {
  return { sql: "SELECT * FROM procuring_entities WHERE pe_id = ?", params: [id] };
}

export function peTopBiddersQuery(id: string): Query {
  return {
    sql:
      "SELECT bidder_id, awardee, COUNT(*) AS n_awards, SUM(COALESCE(value_crore, 0)) AS total_value_crore " +
      "FROM contracts WHERE pe_id = ? AND bidder_id != '' GROUP BY bidder_id, awardee ORDER BY n_awards DESC LIMIT 10",
    params: [id],
  };
}
