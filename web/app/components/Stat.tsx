export function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="border-t-2 border-ink pt-3">
      <div className="eyebrow">{label}</div>
      <div className="num mt-1 text-3xl font-medium text-ink">{typeof value === "number" ? value.toLocaleString("en-IN") : value}</div>
      {hint ? <div className="mt-1 text-xs text-ink-3">{hint}</div> : null}
    </div>
  );
}
