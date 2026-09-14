import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { formatCrore } from "@/lib/format";
import { Stat } from "../../components/Stat";
import { Patterns } from "../../components/Patterns";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const data = await api.pe(id);
  return { title: data?.procuring_entity.name ?? "Procuring entity" };
}

export default async function PePage({ params }: Props) {
  const { id } = await params;
  const data = await api.pe(id);
  if (!data) notFound();
  const pe = data.procuring_entity;
  return (
    <article>
      <p className="eyebrow">Procuring entity</p>
      <h1 className="mt-2 text-3xl font-medium sm:text-4xl">{pe.name}</h1>
      <p className="mt-2 text-ink-2">{pe.ministry}</p>
      <div className="mt-8 grid grid-cols-2 gap-4 sm:max-w-md">
        <Stat label="Tenders indexed" value={pe.n_tenders} />
        <Stat label="Awards indexed" value={pe.n_contracts} />
      </div>
      <Patterns flags={data.flags} kind="entity" />
      <section className="mt-10">
        <h2 className="border-b-2 border-ink pb-2 text-xl">Top bidders</h2>
        {data.top_bidders.length ? (
          <table className="w-full text-sm">
            <thead><tr className="text-left"><th className="eyebrow py-2 font-normal">Bidder</th><th className="eyebrow py-2 text-right font-normal">Awards</th><th className="eyebrow py-2 text-right font-normal">Total value</th></tr></thead>
            <tbody>
              {data.top_bidders.map((b) => (
                <tr key={b.bidder_id} className="border-t border-rule">
                  <td className="py-2 pr-3"><Link href={`/e/${b.bidder_id}`} className="text-ink hover:text-brand">{b.awardee}</Link></td>
                  <td className="num py-2 text-right">{b.n_awards}</td>
                  <td className="num py-2 text-right">{formatCrore(b.total_value_crore) || "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="py-6 text-ink-3">No awards indexed for this entity yet. Winner concentration flags arrive in week 6.</p>
        )}
        <p className="mt-4 text-sm">
          <Link href={`/?status=all&q=${encodeURIComponent(pe.name.split(" ")[0])}`} className="text-brand">Search tenders mentioning this entity</Link>
        </p>
      </section>
    </article>
  );
}
