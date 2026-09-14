export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://bidefy.iba-jobs.workers.dev";

export type Tender = {
  tender_id: string;
  reference: string;
  status: string;
  nature: string;
  title: string;
  ministry: string;
  organization: string;
  procuring_entity: string;
  pe_id: string;
  method: string;
  procurement_type?: string;
  published_at: string | null;
  closing_at: string | null;
  category?: string | null;
  category_confidence?: number | null;
  note?: string;
  awardee?: string | null;
  bidder_id?: string | null;
  value_crore?: number | null;
  signed_on?: string | null;
  district?: string | null;
};
export type Award = {
  tender_id: string;
  title: string;
  awardee?: string;
  bidder_id?: string;
  value_crore: number | null;
  signed_on: string | null;
  procuring_entity?: string;
  pe_id?: string;
  district?: string;
};
export type Bidder = {
  bidder_id: string;
  canonical_name: string;
  variants: string;
  n_awards: number;
  total_value_crore: number;
  first_award: string | null;
  last_award: string | null;
};
export type Prediction = { q10_lakh: number; q50_lakh: number; q90_lakh: number; deferred: number | boolean; model_version: string };
export type PE = { pe_id: string; name: string; ministry: string; n_contracts: number; n_tenders: number };
export type TopBidder = { bidder_id: string; awardee: string; n_awards: number; total_value_crore: number };
export type Stats = {
  live_tenders: number;
  contracts: number;
  bidders: number;
  newest_published: string | null;
  last_fetched: string | null;
};
export type Option = { v: string; n: number };
export type Filters = { ministries: Option[]; districts: Option[]; statuses: Option[]; categories?: Option[] };

async function get<T>(path: string, revalidate = 300): Promise<T | null> {
  try {
    const r = await fetch(`${API_BASE}${path}`, { next: { revalidate } });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  stats: () => get<Stats>("/api/v1/stats", 120),
  filters: () => get<Filters>("/api/v1/filters", 3600),
  tenders: (qs: string) => get<{ page: number; size: number; items: Tender[] }>(`/api/v1/tenders${qs ? "?" + qs : ""}`, 120),
  tender: (id: string) => get<{ tender: Tender; similar_awards: Award[]; prediction: Prediction | null }>(`/api/v1/tenders/${encodeURIComponent(id)}`),
  bidder: (id: string) => get<{ bidder: Bidder; awards: Award[]; flags?: Record<string, unknown> }>(`/api/v1/bidders/${encodeURIComponent(id)}`),
  pe: (id: string) => get<{ procuring_entity: PE; top_bidders: TopBidder[]; recent_awards?: Award[]; flags?: Record<string, unknown> }>(`/api/v1/pe/${encodeURIComponent(id)}`),
};
