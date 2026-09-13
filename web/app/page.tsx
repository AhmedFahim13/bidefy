import { api } from "@/lib/api";
import { buildQuery, formatDate } from "@/lib/format";
import { Filters } from "./components/Filters";
import { Pagination } from "./components/Pagination";
import { Stat } from "./components/Stat";
import { TenderCard } from "./components/TenderCard";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

export default async function Home({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const state = { q: one(sp.q).trim(), status: one(sp.status) || "Live", ministry: one(sp.ministry), category: one(sp.category) };
  const page = Math.max(1, Number.parseInt(one(sp.page) || "1", 10) || 1);
  const size = 25;
  const qs = buildQuery({ ...state, page, size });
  const [stats, options, list] = await Promise.all([api.stats(), api.filters(), api.tenders(qs)]);
  const items = list?.items ?? [];

  return (
    <div>
      <section className="grid gap-6 sm:grid-cols-[1.2fr_1fr] sm:items-end">
        <div>
          <p className="eyebrow">Bangladesh public procurement</p>
          <h1 className="mt-2 text-4xl font-medium leading-tight sm:text-5xl">Every open tender, and who has been winning them.</h1>
          <p className="mt-3 max-w-xl text-ink-2">
            Bidefy indexes the e-GP portal nightly, resolves the firms behind the awards, and alerts you when a tender matching your filters appears. Free for the alerts; intelligence on top.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Live tenders" value={stats?.live_tenders ?? 0} />
          <Stat label="Awards indexed" value={stats?.contracts ?? 0} hint={stats?.contracts ? undefined : "Backfill in progress"} />
          <Stat label="Newest" value={stats?.newest_published ? formatDate(stats.newest_published).split(",")[0] : "n/a"} hint="published" />
        </div>
      </section>

      <section className="mt-10">
        <Filters options={options} state={state} />
      </section>

      <section className="mt-8">
        <div className="flex items-baseline justify-between border-b-2 border-ink pb-2">
          <h2 className="text-xl">{state.status === "all" ? "All tenders" : `${state.status} tenders`}{state.q ? ` matching “${state.q}”` : ""}</h2>
          <span className="num text-xs text-ink-3">{items.length} on this page</span>
        </div>
        {items.length ? (
          <ul>{items.map((t, i) => <TenderCard key={t.tender_id} t={t} index={i} />)}</ul>
        ) : (
          <p className="py-10 text-center text-ink-3">
            {list ? "No tenders match those filters." : "The data service did not respond. Try again in a minute."}
          </p>
        )}
        <Pagination page={page} hasNext={items.length === size} params={state} />
      </section>
    </div>
  );
}
