export type Flags = Record<string, unknown> & { notes?: string[]; awards_12m?: number };

function pct(v: unknown): string {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "n/a";
}

export function Patterns({ flags, kind }: { flags: Flags | null | undefined; kind: "bidder" | "entity" }) {
  const notes = Array.isArray(flags?.notes) ? (flags!.notes as string[]) : [];
  const n = typeof flags?.awards_12m === "number" ? (flags!.awards_12m as number) : 0;
  return (
    <section className="mt-8 border-t-2 border-ink pt-3">
      <p className="eyebrow">Patterns in the last 12 months</p>
      {n === 0 ? (
        <p className="mt-2 text-sm text-ink-3">No awards in the last twelve months, so no patterns to report.</p>
      ) : (
        <>
          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
            <div><dt className="eyebrow">Awards</dt><dd className="num">{n}</dd></div>
            {kind === "entity" ? (
              <>
                <div><dt className="eyebrow">Distinct winners</dt><dd className="num">{String(flags?.winners ?? "n/a")}</dd></div>
                <div><dt className="eyebrow">Top winner share</dt><dd className="num">{pct(flags?.top_share)}</dd></div>
                <div><dt className="eyebrow">Concentration (HHI)</dt><dd className="num">{typeof flags?.hhi === "number" ? (flags!.hhi as number).toFixed(2) : "n/a"}</dd></div>
              </>
            ) : (
              <>
                <div><dt className="eyebrow">Entities</dt><dd className="num">{String(flags?.entities ?? "n/a")}</dd></div>
                <div><dt className="eyebrow">Top entity share</dt><dd className="num">{pct(flags?.top_entity_share)}</dd></div>
                <div><dt className="eyebrow">Outside predicted band</dt><dd className="num">{String((flags?.above_band as number | undefined) ?? 0)} above, {String((flags?.below_band as number | undefined) ?? 0)} below</dd></div>
              </>
            )}
          </dl>
          {notes.length ? (
            <ul className="mt-3 space-y-1 text-sm">
              {notes.map((t) => <li key={t} className="rounded-sm bg-warn-wash px-3 py-1.5 text-warn">{t}</li>)}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-ink-3">Nothing stands out against the thresholds.</p>
          )}
          <p className="mt-2 text-xs text-ink-3">A pattern is not a verdict. These are counts and shares from public award records; concentration can reflect a specialist supplier as easily as anything else.</p>
        </>
      )}
    </section>
  );
}
