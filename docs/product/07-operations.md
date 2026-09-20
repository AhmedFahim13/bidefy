# How it runs, and what happens when it breaks

Figures below are from 2026-09-20. The accuracy page is rewritten by each training run; this page
is maintained by hand and dated.

## The daily cycle

Two scheduled runs a day, at 20:00 and 08:00 UTC, each doing the same work against a different
endpoint.

| Step | Budget | What it does |
|---|---|---|
| Crawl | 180 minutes | Tender notices or contract awards, newest first, stopping at the first page with nothing new |
| Live tender details | 20 minutes | Detail pages for open tenders, which carry the security and the procurement codes |
| Awarded tender details | 60 minutes | Detail pages for tenders already awarded, which is what the models learn the link from |
| Compact | minutes | Merges small Parquet parts so the repository stays a few hundred files |
| Build | minutes | Clean tables, entity resolution, categories, flags |
| Train | minutes | Award model and category model, and the accuracy page they write themselves |
| Load | 40,000 writes | Into D1, live tenders first |

The whole job has a 350 minute ceiling, which those budgets fit inside with roughly 90 minutes to
spare.

## Budgets that shape everything

| Budget | Limit | How it is respected |
|---|---|---|
| Portal politeness | 1 request per second, one session | A crawl takes hours and resumes across nights rather than going faster |
| D1 writes | 100,000 a day, every index entry counted | 40,000 per run inside 80,000 a day, tracked in a watermark that survives restarts |
| D1 statement size | about 100 KB | Statements are batched by bytes, roughly 150 rows each |
| GitHub Actions | 6 hours a job | 350 minute ceiling, every step checkpointed and resumable |
| Push per subscription | 20 an hour | A noisy filter cannot flood a phone |

## What has actually gone wrong

Each of these is now covered by a test or a guard, and each cost real time.

- **A crawl lost twice to line endings.** The nightly commit rebased onto churn in test fixtures and
  failed after four hours of crawling. Fixtures are now binary to git, data is committed before
  anything fallible, and the job cannot lose a crawl to a rebase again.
- **Loads that reported success and wrote nothing.** Wrangler was called as a list with a shell
  flag, which works on Windows and silently runs bare `npx` on Linux. Two nights of loads wrote no
  rows while reporting done. Every load now ends by writing a marker row and reading it back before
  the watermark moves.
- **New notices stopped being crawled.** The choice between backfill and delta was derived from
  whether the cursor had passed the last page, which stops being true when the index grows. A
  finished crawl now records that it finished.
- **One of two daily runs loading nothing.** The write budget was one cap per day, so the first run
  took all of it. Each run now gets its own share.

## If something looks wrong

- **The site says data may be out of date.** The banner appears when the newest crawl is old. Check
  the most recent run in GitHub Actions, then the "d1 load" lines in its log: they say how many rows
  were loaded and whether the marker was confirmed.
- **The site is empty or erroring.** The Worker reads D1 directly; check the health endpoint. The
  site fetches from the Worker server-side, so a failing Worker shows as a failing site.
- **A load says "skipped".** That is the safety net, not a failure. The watermark has not moved and
  the next run re-sends the same rows. The message names the exit code and both output streams.
- **Models look wrong after a change.** Every published category figure pools three runs and prints
  the spread between them, because one run of this model moves by more than a point on its own.

## Where the data sits

Raw crawl output and the clean tables are Parquet in the repository, except the clean tables, which
are rebuilt from the raw parts by every run and deliberately not committed: they are large binaries
that do not compress and were adding tens of megabytes a night. D1 holds the last twelve months and
every live tender. Models are joblib bundles, versioned by a format number so a stale bundle is
skipped rather than served.
