import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-20 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 text-3xl">Nothing filed under that id.</h1>
      <p className="mt-3 text-ink-2">It may not be crawled yet, or the id is wrong.</p>
      <Link href="/" className="mt-6 inline-block text-brand">Back to live tenders</Link>
    </div>
  );
}
