import Link from "next/link";
import type { Tender } from "@/lib/api";
import { categoryLabel } from "@/lib/categories";
import { daysLeft, formatDate } from "@/lib/format";

export function CategoryChip({ category }: { category?: string | null }) {
  if (!category) return null;
  return <span className="rounded-sm bg-brand-wash px-1.5 py-0.5 text-[0.7rem] text-brand">{categoryLabel(category)}</span>;
}

export function StatusPill({ status }: { status: string }) {
  const s = status || "Unknown";
  const tone =
    s === "Live" ? "bg-ok-wash text-ok" : s === "Cancelled" || s === "Rejected" ? "bg-bad-wash text-bad" : "bg-surface-2 text-ink-2";
  return <span className={`inline-block rounded-sm px-2 py-0.5 font-mono text-[0.66rem] uppercase tracking-[0.12em] ${tone}`}>{s}</span>;
}

export function ClosingBadge({ closing }: { closing: string | null }) {
  const d = daysLeft(closing);
  if (d === null) return null;
  if (d < 0) return <span className="text-xs text-ink-3">closed</span>;
  const tone = d <= 3 ? "text-warn" : "text-ink-3";
  return <span className={`num text-xs ${tone}`}>{d === 0 ? "closes today" : `${d} day${d === 1 ? "" : "s"} left`}</span>;
}

export function TenderCard({ t, index = 0 }: { t: Tender; index?: number }) {
  return (
    <li className="rise grid gap-1 border-b border-rule py-4 sm:grid-cols-[1fr_auto] sm:gap-6" style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={t.status} />
          <span className="num text-xs text-ink-3">{t.tender_id}</span>
          {t.method ? <span className="text-xs text-ink-3">{t.method}</span> : null}
          {t.nature ? <span className="text-xs text-ink-3">{t.nature}</span> : null}
          <CategoryChip category={t.category} />
        </div>
        <h3 className="mt-1 text-lg leading-snug">
          <Link href={`/t/${t.tender_id}`} className="text-ink no-underline hover:text-brand hover:underline">{t.title || "Untitled tender"}</Link>
        </h3>
        <div className="mt-1 text-sm text-ink-2">
          <Link href={`/pe/${t.pe_id}`} className="hover:text-brand">{t.procuring_entity}</Link>
          {t.ministry ? <span className="text-ink-3"> · {t.ministry}</span> : null}
        </div>
      </div>
      <div className="flex flex-row gap-4 text-right sm:flex-col sm:gap-0.5">
        <div className="text-xs text-ink-3">Published <span className="num text-ink-2">{formatDate(t.published_at)}</span></div>
        <div className="text-xs text-ink-3">Closes <span className="num text-ink-2">{formatDate(t.closing_at)}</span></div>
        <ClosingBadge closing={t.closing_at} />
      </div>
    </li>
  );
}
