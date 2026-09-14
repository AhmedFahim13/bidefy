import type { Metadata } from "next";
import { api } from "@/lib/api";
import { AlertsForm } from "../components/AlertsForm";

export const metadata: Metadata = { title: "Alerts" };

export default async function AlertsPage() {
  const options = await api.filters();
  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
      <div>
        <p className="eyebrow">Push alerts</p>
        <h1 className="mt-2 text-4xl font-medium leading-tight">Hear about a tender the hour it appears.</h1>
        <p className="mt-3 text-ink-2">
          Pick up to three filters. When a new tender matches one of them, this device gets a notification with the title, the procuring entity and the closing date. Tap it to open the tender.
        </p>
        <ul className="mt-4 space-y-1 text-sm text-ink-2">
          <li>Works in Chrome, Edge and Firefox on Android and desktop.</li>
          <li>On iPhone, install Bidefy to the Home Screen first.</li>
          <li>Stop any time from this page. Nothing is stored except the push endpoint and your filters.</li>
        </ul>
      </div>
      <AlertsForm
        apiBase=""
        ministries={(options?.ministries ?? []).map((m) => m.v)}
        statuses={(options?.statuses ?? []).map((s) => s.v)}
        categories={(options?.categories ?? []).map((c) => c.v)}
      />
    </div>
  );
}
