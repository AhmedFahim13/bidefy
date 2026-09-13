import { api } from "@/lib/api";
import { formatDate, isStale, parseFetchedAt } from "@/lib/format";

export async function StaleBanner() {
  const stats = await api.stats();
  if (stats && !isStale(stats.last_fetched)) return null;
  const when = parseFetchedAt(stats?.last_fetched);
  return (
    <div className="border-b border-warn/30 bg-warn-wash text-warn" role="status">
      <div className="mx-auto max-w-6xl px-4 py-2 text-sm">
        {stats
          ? `Data may be out of date. Last crawl ${when ? formatDate(when.toISOString().slice(0, 16)) + " UTC" : "unknown"}.`
          : "The data service is not responding. Showing nothing rather than something stale."}
      </div>
    </div>
  );
}
