import type { Filters as FilterOptions } from "@/lib/api";
import { categoryLabel } from "@/lib/categories";

export type FilterState = { q: string; status: string; ministry: string; category: string };

const field = "w-full rounded-sm border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-brand";

export function Filters({ options, state }: { options: FilterOptions | null; state: FilterState }) {
  const statuses = options?.statuses ?? [];
  const ministries = options?.ministries ?? [];
  const categories = options?.categories ?? [];
  return (
    <form method="get" action="/" className="grid gap-3 rounded-sm border border-rule bg-surface p-4 shadow-[0_1px_0_rgba(0,0,0,0.03)] sm:grid-cols-[1.3fr_0.7fr_1fr_1fr_auto] sm:items-end">
      <label className="block">
        <span className="eyebrow">Keyword</span>
        <input name="q" defaultValue={state.q} placeholder="printer, road, medicine" className={`${field} mt-1`} />
      </label>
      <label className="block">
        <span className="eyebrow">Status</span>
        <select name="status" defaultValue={state.status} className={`${field} mt-1`}>
          <option value="Live">Live</option>
          <option value="all">All</option>
          {statuses.filter((s) => s.v !== "Live").map((s) => (
            <option key={s.v} value={s.v}>{s.v}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="eyebrow">Ministry</span>
        <select name="ministry" defaultValue={state.ministry} className={`${field} mt-1`}>
          <option value="">Any ministry</option>
          {ministries.map((m) => (
            <option key={m.v} value={m.v}>{m.v}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="eyebrow">Category</span>
        <select name="category" defaultValue={state.category} className={`${field} mt-1`}>
          <option value="">Any category</option>
          {categories.map((c) => (
            <option key={c.v} value={c.v}>{categoryLabel(c.v)} ({c.n})</option>
          ))}
        </select>
      </label>
      <button type="submit" className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-deep">Search</button>
    </form>
  );
}
