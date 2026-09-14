import type { Metadata } from "next";
import { GLOSSARY } from "@/lib/glossary";

export const metadata: Metadata = { title: "How a tender works" };

const STEPS: { title: string; body: string; bidefy: string }[] = [
  { title: "A buyer decides to spend", body: "A procuring entity, say a district hospital, has budget for something: medicine, a road, cleaning services. It files an annual procurement plan and picks a method, usually open tendering.", bidefy: "Nothing yet. Bidefy starts at the next step." },
  { title: "The tender is published", body: "The invitation appears on e-GP with a title, the buying entity, the method, a closing date and a security amount. The full document costs a small fee to download.", bidefy: "Within an hour Bidefy indexes it, predicts its category, estimates the award band from that entity's history, and notifies subscribers whose filters match." },
  { title: "Firms bid", body: "Bidders lodge the security and submit priced offers before closing. Corrigenda may move the date. Late bids are rejected.", bidefy: "This is where the band earns its keep: a bidder prices with a view of what this entity has paid for similar work, and who usually wins there." },
  { title: "Evaluation", body: "The status becomes Being processed. A committee checks eligibility and scores bids; for most goods and works the lowest responsive price wins.", bidefy: "Nothing is public during this stage, so Bidefy shows nothing new." },
  { title: "Award and contract", body: "The buyer publishes a Notification of Award naming the winner and the value, then signs the contract. If no valid bids came in, it re-tenders.", bidefy: "The award joins the index, the winner's profile updates, and the entity's concentration numbers move. The model retrains on it that night." },
];

export default function LearnPage() {
  return (
    <div className="grid gap-12 lg:grid-cols-[1.2fr_1fr]">
      <div>
        <p className="eyebrow">How a tender works in Bangladesh</p>
        <h1 className="mt-2 text-4xl font-medium leading-tight">From notice to award, and what Bidefy adds at each step.</h1>
        <p className="mt-3 text-ink-2">
          Public bodies in Bangladesh buy almost everything through one portal, e-GP. Every notice and every award is public. Bidefy reads those pages nightly and turns them into something a bidder can act on.
        </p>
        <ol className="mt-8 space-y-6">
          {STEPS.map((s, i) => (
            <li key={s.title} className="grid gap-2 border-t border-rule pt-4 sm:grid-cols-[2rem_1fr]">
              <span className="num text-2xl text-ink-3">{i + 1}</span>
              <div>
                <h2 className="text-xl">{s.title}</h2>
                <p className="mt-1 text-sm text-ink-2">{s.body}</p>
                <p className="mt-2 rounded-sm bg-brand-wash px-3 py-2 text-sm text-brand-deep"><span className="eyebrow text-brand">Bidefy</span> {s.bidefy}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
      <aside>
        <h2 className="border-b-2 border-ink pb-2 text-xl">Glossary</h2>
        <dl className="mt-3">
          {GLOSSARY.map((t) => (
            <div key={t.key} id={t.key} className="border-b border-rule py-3">
              <dt className="font-medium">{t.term}</dt>
              <dd className="mt-1 text-sm text-ink-2">{t.short}{t.long ? <span className="block mt-1 text-ink-3">{t.long}</span> : null}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </div>
  );
}
