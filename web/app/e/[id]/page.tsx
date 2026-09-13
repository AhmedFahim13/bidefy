import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { formatCrore, formatDate } from "@/lib/format";
import { Stat } from "../../components/Stat";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const data = await api.bidder(id);
  return { title: data?.bidder.canonical_name ?? "Bidder" };
}

export default async function BidderPage({ params }: Props) {
  const { id } = await params;
  const data = await api.bidder(id);
  if (!data) notFound();
  const b = data.bidder;
  let variants: string[] = [];
  try { variants = JSON.parse(b.variants || "[]"); } catch { variants = []; }
  const aliases = variants.filter((v) => v !== b.canonical_name);
  return (
    <article>
      <p className="eyebrow">Bidder</p>
      <h1 className="mt-2 text-3xl font-medium sm:text-4xl">{b.canonical_name}</h1>
      {aliases.length ? (
        <p className="mt-2 text-sm text-ink-3">
          Also appears as {aliases.map((a, i) => (
            <span key={a}><span className="rounded-sm bg-surface-2 px-1.5 py-0.5 text-ink-2">{a}</span>{i < aliases.length - 1 ? " " : ""}</span>
          ))}
        </p>
      ) : null}
      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Awards" value={b.n_awards} />
        <Stat label="Total value" value={formatCrore(b.total_value_crore) || "n/a"} />
        <Stat label="First award" value={formatDate(b.first_award) || "n/a"} />
        <Stat label="Latest award" value={formatDate(b.last_award) || "n/a"} />
      </div>
      <section className="mt-10">
        <h2 className="border-b-2 border-ink pb-2 text-xl">Awards</h2>
        {data.awards.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="text-left"><th className="eyebrow py-2 font-normal">Tender</th><th className="eyebrow py-2 font-normal">Entity</th><th className="eyebrow py-2 font-normal">District</th><th className="eyebrow py-2 text-right font-normal">Value</th><th className="eyebrow py-2 text-right font-normal">Signed</th></tr></thead>
              <tbody>
                {data.awards.map((a) => (
                  <tr key={a.tender_id} className="border-t border-rule">
                    <td className="py-2 pr-3"><Link href={`/t/${a.tender_id}`} className="text-ink hover:text-brand">{a.title}</Link></td>
                    <td className="py-2 pr-3 text-ink-2">{a.pe_id ? <Link href={`/pe/${a.pe_id}`} className="hover:text-brand">{a.procuring_entity}</Link> : a.procuring_entity}</td>
                    <td className="py-2 pr-3 text-ink-2">{a.district}</td>
                    <td className="num py-2 text-right">{formatCrore(a.value_crore) || "n/a"}</td>
                    <td className="num py-2 text-right text-ink-2">{formatDate(a.signed_on)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-6 text-ink-3">No awards indexed yet.</p>
        )}
      </section>
    </article>
  );
}
