import type { Metadata } from "next";
import Link from "next/link";
import { AccessForm } from "../components/AccessForm";

export const metadata: Metadata = {
  title: "Pricing",
  description: "What the free tier covers, what Pro adds, and why the Pro price is not settled yet.",
};

/**
 * Two rows per feature so the difference is legible without a tick-and-cross grid, which always
 * ends up flattering the paid column. Where Pro's value rests on a measured number, the number is
 * named here rather than described, and it links to the page that shows how it was measured.
 */
const ROWS: { feature: string; free: string; pro: string }[] = [
  { feature: "Every live tender, searchable",
    free: "Yes, the whole portal",
    pro: "Yes, the whole portal" },
  { feature: "Filters",
    free: "Keyword, status, ministry, category",
    pro: "The same, plus district and buyer" },
  { feature: "Web push alerts",
    free: "Three saved filters",
    pro: "Unlimited saved filters" },
  { feature: "What a tender will be awarded for",
    free: "Not shown",
    pro: "A band on every live tender, with its coverage stated" },
  { feature: "Who has been winning this kind of work",
    free: "The award and the winner",
    pro: "Full bidder and buyer profiles, with history and totals" },
  { feature: "Repeat-winner concentration flags",
    free: "Not shown",
    pro: "Shown, with the numbers behind each flag" },
  { feature: "Export and integration",
    free: "Not available",
    pro: "CSV export and an API key" },
];

export default function PricingPage() {
  return (
    <div className="grid gap-12">
      <section className="max-w-3xl">
        <p className="eyebrow">Pricing</p>
        <h1 className="mt-2 text-4xl font-medium leading-tight sm:text-5xl">
          The alerts are free. The intelligence is what costs.
        </h1>
        <p className="mt-4 text-ink-2">
          Bidefy reads Bangladesh&rsquo;s e-GP portal every night, resolves the firms behind the
          awards, and estimates what a live tender will be awarded for. Finding a tender should not
          cost anything, so it does not. What costs is the part that took the archive to build.
        </p>
      </section>

      <section>
        <div className="flex items-baseline justify-between border-b-2 border-ink pb-2">
          <h2 className="text-xl">What each tier covers</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="mt-4 w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-rule text-left">
                <th className="py-2 pr-4 font-medium text-ink-2">&nbsp;</th>
                <th className="py-2 pr-4 font-medium">Free</th>
                <th className="py-2 font-medium">Pro</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.feature} className="border-b border-rule align-top">
                  <th scope="row" className="py-3 pr-4 text-left font-medium text-ink">{r.feature}</th>
                  <td className="py-3 pr-4 text-ink-2">{r.free}</td>
                  <td className="py-3 text-ink-2">{r.pro}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-6 sm:grid-cols-2">
        <div className="rounded-sm border border-rule bg-surface p-5">
          <p className="eyebrow">Free</p>
          <p className="num mt-1 text-3xl font-medium">0 taka</p>
          <p className="mt-2 text-sm text-ink-2">
            Free permanently, not free for now. The portal&rsquo;s own notices are public and the
            crawl costs nothing to run, so there is no honest reason to charge for finding a tender.
          </p>
          <p className="mt-3 text-sm">
            <Link href="/alerts" className="text-brand">Set up alerts</Link>
          </p>
        </div>
        <div className="rounded-sm border border-rule bg-surface p-5">
          <p className="eyebrow">Pro</p>
          <p className="num mt-1 text-3xl font-medium">Not set yet</p>
          <p className="mt-2 text-sm text-ink-2">
            A number could be put here, and it would be a guess. Nothing is charged, no payment rail
            is connected, and the figure will be set from what the first users say they already pay
            for tender information today &mdash; which is the question the form below leads with.
            Until those answers exist, a made-up price would be the first dishonest number on a site
            built to publish honest ones.
          </p>
          <p className="mt-3 text-sm text-ink-2">The first group gets Pro free, for feedback.</p>
        </div>
      </section>

      <section className="max-w-3xl">
        <div className="flex items-baseline justify-between border-b-2 border-ink pb-2">
          <h2 className="text-xl">Before you pay for a number, read how it was measured</h2>
        </div>
        <p className="mt-4 text-ink-2">
          Pro&rsquo;s value rests on estimates, and an estimate without an error rate is a
          decoration. So every figure Bidefy publishes is measured on awards the model had not seen,
          reported next to how often it declines to answer, and rewritten by the training run itself
          so the page cannot drift from the model. Where the numbers are weak, the page says so: the
          tenders that publish no tender security get a band several times wider than the ones that
          do, and both are printed.
        </p>
        <p className="mt-3 text-sm">
          <Link href="/learn" className="text-brand">How the portal works, and what the terms mean</Link>
          <span className="text-ink-3"> &middot; </span>
          <a href="https://ahmedfahim13.github.io/bidefy/doc.html" className="text-brand">
            What it gets right, and how often
          </a>
        </p>
      </section>

      <section className="grid gap-8 lg:grid-cols-[1fr_1.3fr]">
        <div>
          <div className="border-b-2 border-ink pb-2">
            <h2 className="text-xl">Ask for Pro</h2>
          </div>
          <p className="mt-4 text-sm text-ink-2">
            Tell us what you bid on and what you pay today for the same information. That answer is
            what sets the price, so it is the only question here that really matters.
          </p>
          <p className="mt-3 text-sm text-ink-3">
            No card, no account. A contact and a sentence is enough.
          </p>
        </div>
        <AccessForm apiBase="" />
      </section>
    </div>
  );
}
