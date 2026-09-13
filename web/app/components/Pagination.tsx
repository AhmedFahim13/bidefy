import Link from "next/link";
import { buildQuery } from "@/lib/format";

export function Pagination({ page, hasNext, params }: { page: number; hasNext: boolean; params: Record<string, string> }) {
  const link = (p: number) => {
    const qs = buildQuery({ ...params, page: p });
    return qs ? `/?${qs}` : "/";
  };
  const cls = "rounded-sm border border-rule px-3 py-1.5 text-sm text-ink-2 hover:border-brand hover:text-brand";
  const disabled = "rounded-sm border border-rule px-3 py-1.5 text-sm text-ink-3/60";
  return (
    <nav className="mt-6 flex items-center justify-between" aria-label="Pagination">
      {page > 1 ? <Link href={link(page - 1)} className={cls}>Previous</Link> : <span className={disabled}>Previous</span>}
      <span className="num text-xs text-ink-3">Page {page}</span>
      {hasNext ? <Link href={link(page + 1)} className={cls}>Next</Link> : <span className={disabled}>Next</span>}
    </nav>
  );
}
