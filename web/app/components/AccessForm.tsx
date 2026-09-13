"use client";

import { useState } from "react";

const BANDS: { v: string; label: string }[] = [
  { v: "under_10_lakh", label: "Under 10 lakh" },
  { v: "10_lakh_to_1_crore", label: "10 lakh to 1 crore" },
  { v: "1_to_10_crore", label: "1 to 10 crore" },
  { v: "over_10_crore", label: "Over 10 crore" },
];
const field = "w-full rounded-sm border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-brand";

export function AccessForm({ apiBase }: { apiBase: string }) {
  const [form, setForm] = useState({ name: "", organisation: "", role: "", bids_on: "", value_band: "1_to_10_crore", contact: "", note: "", website: "" });
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState("");
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("busy");
    setError("");
    try {
      const r = await fetch(`${apiBase}/api/v1/access-requests`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(form) });
      if (!r.ok) {
        const err = (await r.json().catch(() => ({}))) as { error?: string };
        throw new Error(err.error ?? "The request was not accepted.");
      }
      setState("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setState("idle");
    }
  };

  if (state === "done") {
    return (
      <div className="rounded-sm border border-ok/30 bg-ok-wash p-5 text-ok">
        <p className="font-medium">Request received.</p>
        <p className="mt-1 text-sm">You are on the list. Pro opens to a small group first, and the people on this list hear first.</p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-sm border border-rule bg-surface p-4 sm:p-6">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block"><span className="eyebrow">Your name</span><input required value={form.name} onChange={set("name")} className={`${field} mt-1`} /></label>
        <label className="block"><span className="eyebrow">Organisation</span><input required value={form.organisation} onChange={set("organisation")} className={`${field} mt-1`} /></label>
        <label className="block"><span className="eyebrow">Role</span><input value={form.role} onChange={set("role")} placeholder="Owner, tender desk, finance" className={`${field} mt-1`} /></label>
        <label className="block"><span className="eyebrow">Contact (email or phone)</span><input value={form.contact} onChange={set("contact")} className={`${field} mt-1`} /></label>
      </div>
      <label className="block"><span className="eyebrow">What do you bid on?</span><input required value={form.bids_on} onChange={set("bids_on")} placeholder="e.g. LGED rural roads in Rangpur, hospital supplies nationwide" className={`${field} mt-1`} /></label>
      <label className="block"><span className="eyebrow">Typical tender value</span>
        <select value={form.value_band} onChange={set("value_band")} className={`${field} mt-1`}>
          {BANDS.map((b) => <option key={b.v} value={b.v}>{b.label}</option>)}
        </select>
      </label>
      <label className="block"><span className="eyebrow">Anything else</span><textarea value={form.note} onChange={set("note")} rows={3} placeholder="What would make this worth paying for?" className={`${field} mt-1`} /></label>
      <input type="text" name="website" value={form.website} onChange={set("website")} className="hidden" tabIndex={-1} autoComplete="off" aria-hidden="true" />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={state === "busy"} className="rounded-sm bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-deep disabled:opacity-60">
          {state === "busy" ? "Sending" : "Request access"}
        </button>
        <span className="text-xs text-ink-3">No payment. No account. We only use this to decide what to build and who to call first.</span>
      </div>
      {error ? <p className="rounded-sm bg-bad-wash px-3 py-2 text-sm text-bad">{error}</p> : null}
    </form>
  );
}
