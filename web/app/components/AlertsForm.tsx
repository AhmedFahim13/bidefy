"use client";

import { useEffect, useState } from "react";
import { loadSaved, pushSupported, subscribeToPush, unsubscribeFromPush, type Filter, type SavedSubscription } from "@/lib/push";

import { categoryLabel } from "@/lib/categories";

type Props = { apiBase: string; ministries: string[]; statuses: string[]; categories: string[] };
const MAX = 3;
const field = "w-full rounded-sm border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-brand";

function isStandalone(): boolean {
  return typeof window !== "undefined" && (window.matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true);
}

export function AlertsForm({ apiBase, ministries, statuses, categories }: Props) {
  const [rows, setRows] = useState<Filter[]>([{ q: "", ministry: "", status: "Live", category: "" }]);
  const [saved, setSaved] = useState<SavedSubscription | null>(null);
  const [supported, setSupported] = useState<boolean | null>(null);
  const [ios, setIos] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    setSupported(pushSupported());
    setIos(/iPhone|iPad|iPod/.test(navigator.userAgent) && !isStandalone());
    const s = loadSaved();
    if (s) {
      setSaved(s);
      setRows(s.filters.map((f) => ({ q: f.q ?? "", ministry: f.ministry ?? "", status: f.status ?? "", category: f.category ?? "" })));
    }
  }, []);

  const update = (i: number, patch: Partial<Filter>) => setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const remove = (i: number) => setRows((r) => (r.length > 1 ? r.filter((_, j) => j !== i) : r));
  const add = () => setRows((r) => (r.length < MAX ? [...r, { q: "", ministry: "", status: "Live", category: "" }] : r));

  const enable = async () => {
    setBusy(true);
    setError("");
    try {
      const clean = rows
        .map((r) => {
          const f: Filter = {};
          if (r.q?.trim()) f.q = r.q.trim();
          if (r.ministry) f.ministry = r.ministry;
          if (r.status && r.status !== "any") f.status = r.status;
          if (r.category) f.category = r.category;
          return f;
        })
        .filter((f) => Object.keys(f).length);
      if (!clean.length) throw new Error("Add at least one keyword, ministry or status.");
      setSaved(await subscribeToPush(apiBase, clean));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    setError("");
    try {
      await unsubscribeFromPush(apiBase);
      setSaved(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  if (supported === false) {
    return (
      <div className="rounded-sm border border-warn/30 bg-warn-wash p-4 text-sm text-warn">
        {ios
          ? "On iPhone, alerts work after you add Bidefy to your Home Screen: tap Share, then Add to Home Screen, then open it from there."
          : "This browser does not support web push. Chrome, Edge and Firefox on Android and desktop do."}
      </div>
    );
  }

  return (
    <div className="rounded-sm border border-rule bg-surface p-4 sm:p-6">
      {saved ? (
        <p className="mb-4 rounded-sm bg-ok-wash px-3 py-2 text-sm text-ok">
          Alerts are on for this device. Subscription <span className="num">{saved.id.slice(0, 8)}</span>. Change the filters and enable again to update them.
        </p>
      ) : null}
      <div className="grid gap-3">
        {rows.map((r, i) => (
          <div key={i} className="grid gap-2 rounded-sm border border-rule p-3 sm:grid-cols-[1.2fr_1fr_1fr_0.8fr_auto] sm:items-end">
            <label className="block">
              <span className="eyebrow">Keyword</span>
              <input value={r.q ?? ""} onChange={(e) => update(i, { q: e.target.value })} placeholder="e.g. printer, bridge, vaccine" className={`${field} mt-1`} />
            </label>
            <label className="block">
              <span className="eyebrow">Category</span>
              <select value={r.category ?? ""} onChange={(e) => update(i, { category: e.target.value })} className={`${field} mt-1`}>
                <option value="">Any category</option>
                {categories.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="eyebrow">Ministry</span>
              <select value={r.ministry ?? ""} onChange={(e) => update(i, { ministry: e.target.value })} className={`${field} mt-1`}>
                <option value="">Any ministry</option>
                {ministries.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="eyebrow">Status</span>
              <select value={r.status ?? "Live"} onChange={(e) => update(i, { status: e.target.value })} className={`${field} mt-1`}>
                <option value="Live">Live</option>
                <option value="any">Any</option>
                {statuses.filter((s) => s !== "Live").map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <button type="button" onClick={() => remove(i)} disabled={rows.length === 1} className="rounded-sm border border-rule px-3 py-2 text-sm text-ink-3 hover:text-bad disabled:opacity-40" aria-label="Remove filter">Remove</button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" onClick={add} disabled={rows.length >= MAX} className="rounded-sm border border-rule px-3 py-2 text-sm text-ink-2 hover:border-brand hover:text-brand disabled:opacity-40">
          Add filter ({rows.length}/{MAX})
        </button>
        <button type="button" onClick={enable} disabled={busy} className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-deep disabled:opacity-60">
          {busy ? "Working" : saved ? "Update alerts" : "Enable alerts"}
        </button>
        {saved ? (
          <button type="button" onClick={disable} disabled={busy} className="text-sm text-ink-3 hover:text-bad">Stop alerts</button>
        ) : null}
      </div>
      {error ? <p className="mt-3 rounded-sm bg-bad-wash px-3 py-2 text-sm text-bad">{error}</p> : null}
      <p className="mt-4 text-xs text-ink-3">
        Free tier: up to three filters on this device. Bidefy checks for new matching tenders every hour and sends one notification per tender. No account, no email.
      </p>
    </div>
  );
}
