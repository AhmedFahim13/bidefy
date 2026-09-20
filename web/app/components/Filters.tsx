"use client";

import { useRef } from "react";
import type { Filters as FilterOptions } from "@/lib/api";
import { categoryLabel } from "@/lib/categories";

export type FilterState = { q: string; status: string; ministry: string; category: string };

const field = "w-full rounded-sm border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-brand";

export function Filters({ options, state }: { options: FilterOptions | null; state: FilterState }) {
  const form = useRef<HTMLFormElement>(null);
  const category = useRef<HTMLSelectElement>(null);
  const statuses = options?.statuses ?? [];
  const ministries = options?.ministries ?? [];
  const categories = options?.categories ?? [];
  // The counts already follow the other filters, so a ministry's dropdown lists only what that
  // ministry buys. Keep whatever is selected visible even when the count is now zero, or the
  // select would silently fall back to "any".
  const keep = (list: { v: string; n: number }[], selected: string) =>
    selected && !list.some((o) => o.v === selected) ? [...list, { v: selected, n: 0 }] : list;
  const shownCategories = keep(categories, state.category);
  const shownMinistries = keep(ministries, state.ministry);

  // Changing a dropdown searches straight away, so the other dropdowns show counts for what was
  // just chosen rather than waiting for the button. The button still works without JavaScript.
  const submit = () => form.current?.requestSubmit();
  const onMinistryChange = () => {
    if (category.current) category.current.value = "";   // last ministry's category may not exist here
    submit();
  };

  return (
    <form ref={form} method="get" action="/" className="grid gap-3 rounded-sm border border-rule bg-surface p-4 shadow-[0_1px_0_rgba(0,0,0,0.03)] sm:grid-cols-[1.3fr_0.7fr_1fr_1fr_auto] sm:items-end">
      <label className="block">
        <span className="eyebrow">Keyword</span>
        <input name="q" defaultValue={state.q} placeholder="printer, road, medicine" className={`${field} mt-1`} />
      </label>
      <label className="block">
        <span className="eyebrow">Status</span>
        <select name="status" defaultValue={state.status} onChange={submit} className={`${field} mt-1`}>
          <option value="Live">Live</option>
          <option value="all">All</option>
          {statuses.filter((s) => s.v !== "Live").map((s) => (
            <option key={s.v} value={s.v}>{s.v}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="eyebrow">Ministry</span>
        <select name="ministry" defaultValue={state.ministry} onChange={onMinistryChange} className={`${field} mt-1`}>
          <option value="">Any ministry</option>
          {shownMinistries.map((m) => (
            <option key={m.v} value={m.v}>{m.v} ({m.n})</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="eyebrow">Category</span>
        <select ref={category} name="category" defaultValue={state.category} onChange={submit} className={`${field} mt-1`}>
          <option value="">Any category</option>
          {shownCategories.map((c) => (
            <option key={c.v} value={c.v}>{categoryLabel(c.v)} ({c.n})</option>
          ))}
        </select>
        <span className="mt-1 block text-xs text-ink-3">
          {state.ministry ? "Counts are for this ministry." : "Pick a ministry to see its own categories."}
        </span>
      </label>
      <button type="submit" className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-deep">Search</button>
    </form>
  );
}
