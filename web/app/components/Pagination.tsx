import Link from "next/link";
import { buildQuery } from "@/lib/format";

export const PAGE_SIZES = [25, 50, 100];

export function Pagination({ page, size, hasNext, params }: { page: number; size: number; hasNext: boolean; params: Record<string, string> }) {
  const link = (p: number) => {
    const qs = buildQuery({ ...params, size: size === 25 ? "" : size, page: p });
    return qs ? `/?${qs}` : "/";
  };
  const cls = "rounded-sm border border-rule px-3 py-1.5 text-sm text-ink-2 hover:border-brand hover:text-brand";
  const disabled = "rounded-sm border border-rule px-3 py-1.5 text-sm text-ink-3/60";
  const field = "rounded-sm border border-rule bg-surface px-2 py-1 text-sm text-ink";
  return (
    <nav className="mt-6 flex flex-wrap items-center justify-between gap-3" aria-label="Pagination">
      <div className="flex items-center gap-2">
        {page > 1 ? <Link href={link(page - 1)} className={cls}>Previous</Link> : <span className={disabled}>Previous</span>}
        {hasNext ? <Link href={link(page + 1)} className={cls}>Next</Link> : <span className={disabled}>Next</span>}
      </div>
      <form method="get" action="/" className="flex items-center gap-2 text-sm">
        {Object.entries(params).map(([k, v]) => (v && !(k === "status" && v === "Live") ? <input key={k} type="hidden" name={k} value={v} /> : null))}
        <label className="flex items-center gap-1 text-ink-3">
          Page
          <input type="number" name="page" min={1} defaultValue={page} className={`${field} num w-20`} aria-label="Page number" />
        </label>
        <label className="flex items-center gap-1 text-ink-3">
          Show
          <select name="size" defaultValue={size} className={field} aria-label="Rows per page">
            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <button type="submit" className="rounded-sm border border-rule px-3 py-1 text-sm text-ink-2 hover:border-brand hover:text-brand">Go</button>
      </form>
    </nav>
  );
}
