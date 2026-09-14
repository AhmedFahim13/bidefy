import Link from "next/link";
import { define } from "@/lib/glossary";

/** An e-GP abbreviation with its definition on hover and a link to the learn page. */
export function Term({ value }: { value: string | null | undefined }) {
  if (!value) return null;
  const d = define(value);
  if (!d) return <span className="text-xs text-ink-3">{value}</span>;
  return (
    <Link href="/learn" title={d} className="text-xs text-ink-3 underline decoration-dotted decoration-ink-3/60 underline-offset-2 hover:text-brand">
      {value}
    </Link>
  );
}
