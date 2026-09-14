# Bidefy

Live site: https://bidefy.vercel.app
Status: v0.1 public. Free tier: live tenders, search, categories, up to three push alert filters, award bands, profiles with concentration flags.
New to tenders? Read https://bidefy.vercel.app/learn or docs/product/04-primer.md.
Browser calls go through the site's /api proxy because some ISPs block workers.dev.

Tender intelligence for Bangladesh's public e-GP procurement portal.

- Design spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`
- Command centre: https://ahmedfahim13.github.io/bidefy/ (dashboard) and https://ahmedfahim13.github.io/bidefy/doc.html (product document)

## Crawler

```bash
uv sync
uv run pytest
uv run python -m bidefy.crawler.run --endpoint tenders --mode backfill --budget-min 60
uv run python -m bidefy.crawler.run --endpoint tenders --mode delta
```

Runs nightly on GitHub Actions at one request per second, checkpointed in `checkpoints/`,
data committed under `data/raw/`. Backfill resumes across nights until `next_page` passes
`total_pages`; scheduled runs then switch to delta automatically.

## Worker API

Live at `https://bidefy.iba-jobs.workers.dev`. Routes: `/api/v1/health`,
`/api/v1/tenders?q=&status=&ministry=&page=&size=`, `/api/v1/tenders/:id`,
`/api/v1/bidders/:id`, `/api/v1/pe/:id`. Data is loaded from `data/clean/` into D1
within the free tier's 100,000 row writes a day.

```bash
cd worker && npm install && npm test && npm run typecheck
npm run schema:remote          # once
npx wrangler deploy
cd .. && uv run python -m bidefy.export.d1 --max-rows 90000   # nightly-sized load
```

## Web app

Next.js on Vercel, in `web/`. Server-rendered from the Worker API with short revalidation.

```bash
cd web && npm install && npm test && npm run build
npx vercel --prod --yes     # deploy; NEXT_PUBLIC_API_BASE is set on the Vercel project
```
