import type { Metadata } from "next";
import { API_BASE } from "@/lib/api";
import { AccessForm } from "../components/AccessForm";

export const metadata: Metadata = { title: "Request access to Pro" };

export default function AccessPage() {
  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_1.3fr]">
      <div>
        <p className="eyebrow">Bidefy Pro</p>
        <h1 className="mt-2 text-4xl font-medium leading-tight">Know who wins before you price the bid.</h1>
        <p className="mt-3 text-ink-2">
          The free tier is live tenders, search, categories and three alert filters. Pro is the intelligence on top, built from every contract award on the portal.
        </p>
        <ul className="mt-4 space-y-2 text-sm text-ink-2">
          <li><span className="font-medium text-ink">Award-value bands</span> on every live tender, with the coverage stated.</li>
          <li><span className="font-medium text-ink">Bidder and entity profiles</span>: who wins where, how often, at what value.</li>
          <li><span className="font-medium text-ink">Unlimited alert filters</span>, CSV export and an API key.</li>
          <li><span className="font-medium text-ink">Concentration flags</span> that show repeat-winner patterns with the numbers behind them.</li>
        </ul>
        <p className="mt-6 rounded-sm border border-rule bg-surface p-4 text-sm">
          <span className="eyebrow">Planned price</span><br />
          <span className="num text-2xl font-medium">2,500 taka</span> a month, placeholder. Nothing is charged yet. The first group gets it free in exchange for feedback.
        </p>
      </div>
      <AccessForm apiBase={API_BASE} />
    </div>
  );
}
