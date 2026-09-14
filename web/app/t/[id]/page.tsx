import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { formatCrore, formatDate, formatLakh } from "@/lib/format";
import { CategoryChip, ClosingBadge, StatusPill } from "../../components/TenderCard";
import { Term } from "../../components/Term";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const data = await api.tender(id);
  return { title: data?.tender.title ? data.tender.title.slice(0, 80) : `Tender ${id}` };
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 border-b border-rule py-2 text-sm">
      <dt className="eyebrow pt-0.5">{k}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  );
}

export default async function TenderPage({ params }: Props) {
  const { id } = await params;
  const data = await api.tender(id);
  if (!data) notFound();
  const t = data.tender;
  return (
    <article className="grid gap-10 lg:grid-cols-[1.5fr_1fr]">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={t.status} />
          <span className="num text-xs text-ink-3">{t.tender_id}</span>
          <CategoryChip category={t.category} />
          <ClosingBadge closing={t.closing_at} />
        </div>
        <h1 className="mt-3 text-3xl font-medium leading-tight sm:text-4xl">{t.title || "Untitled tender"}</h1>
        {t.note ? <p className="mt-2 text-sm text-warn">{t.note}</p> : null}
        <dl className="mt-6">
          <Row k="Reference"><span className="num">{t.reference || "n/a"}</span></Row>
          <Row k="Procuring entity"><Link href={`/pe/${t.pe_id}`} className="text-brand">{t.procuring_entity}</Link></Row>
          <Row k="Ministry">{t.ministry}{t.organization ? <span className="text-ink-3"> · {t.organization}</span> : null}</Row>
          <Row k="Nature">{t.nature || "n/a"}</Row>
          <Row k="Method"><Term value={t.method} />{t.procurement_type ? <span className="text-ink-3"> · <Term value={t.procurement_type} /></span> : null} <Link href="/learn" className="ml-2 text-xs text-brand">What these terms mean</Link></Row>
          <Row k="Published"><span className="num">{formatDate(t.published_at) || "n/a"}</span></Row>
          <Row k="Closes"><span className="num">{formatDate(t.closing_at) || "n/a"}</span></Row>
        </dl>
        {t.awardee ? (
          <section className="mt-8 rounded-sm border border-ok/30 bg-ok-wash p-4">
            <p className="eyebrow text-ok">Awarded</p>
            <p className="mt-1 text-lg">
              {t.bidder_id ? <Link href={`/e/${t.bidder_id}`} className="text-ink">{t.awardee}</Link> : t.awardee}
            </p>
            <p className="num mt-1 text-sm text-ink-2">
              {formatCrore(t.value_crore ?? null) || "value not published"}{t.signed_on ? ` · signed ${formatDate(t.signed_on)}` : ""}
            </p>
          </section>
        ) : null}
        <p className="mt-6 text-xs text-ink-3">
          Source: <a href={`https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id=${t.tender_id}&h=t`} rel="noreferrer" className="text-ink-3 underline">tender notice on e-GP</a>
        </p>
      </div>
      <aside>
        <div className="border-t-2 border-ink pt-3">
          <p className="eyebrow">Predicted award band</p>
          {data.prediction && !data.prediction.deferred ? (
            <div className="mt-2">
              <span className={`inline-block rounded-sm px-2 py-0.5 font-mono text-[0.66rem] uppercase tracking-[0.12em] ${data.prediction.basis === "security" ? "bg-ok-wash text-ok" : "bg-surface-2 text-ink-2"}`}>
                {data.prediction.basis === "security" ? "from tender security" : "from entity history"}
              </span>
              <p className="num mt-1 text-2xl font-medium">{formatLakh(data.prediction.q10_lakh)} to {formatLakh(data.prediction.q90_lakh)}</p>
              <p className="mt-1 text-sm text-ink-2">Most likely near <span className="num">{formatLakh(data.prediction.q50_lakh)}</span>.</p>
              <p className="mt-2 text-xs text-ink-3">
                {data.prediction.basis === "security"
                  ? "Derived from the refundable tender security in this notice. Buyers set it as a fixed share of their own cost estimate, so it pins the likely award closely. On held-out awards this route lands within 8 percent of the real value and its band holds about 85 percent of the time."
                  : "Derived from this entity's award history with the ministry, method, category and the wording of the title. No security is published for this tender, so the band is wider. On held-out awards bands like this one hold about three times in four."}
                {" "}Model {data.prediction.model_version}.
              </p>
            </div>
          ) : data.prediction ? (
            <p className="mt-2 text-sm text-ink-3">No band for this tender. The entity has too little award history, or the band would be too wide to be useful. Bidefy declines rather than guesses.</p>
          ) : (
            <p className="mt-2 text-sm text-ink-3">No band yet. Bands appear for live tenders once the award model has run against this entity's history.</p>
          )}
        </div>
        <div className="mt-8 border-t-2 border-ink pt-3">
          <p className="eyebrow">Recent awards by this entity</p>
          {data.similar_awards.length ? (
            <ul className="mt-2">
              {data.similar_awards.map((a) => (
                <li key={a.tender_id} className="border-b border-rule py-2 text-sm">
                  <Link href={`/t/${a.tender_id}`} className="text-ink hover:text-brand">{a.title}</Link>
                  <div className="mt-0.5 text-xs text-ink-3">
                    {a.bidder_id ? <Link href={`/e/${a.bidder_id}`} className="text-ink-2">{a.awardee}</Link> : a.awardee}
                    <span className="num"> · {formatCrore(a.value_crore) || "n/a"} · {formatDate(a.signed_on)}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-ink-3">No awards indexed for this entity yet. The contracts backfill is running.</p>
          )}
        </div>
      </aside>
    </article>
  );
}
