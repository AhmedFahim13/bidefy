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

## Nothing is allowed to fail quietly

Every incident this project has had is one shape. Two crawlers raced a single checkpoint and both
reported success. A `shell=True` call ran bare `npx`, wrote nothing to D1 for days, and exited zero.
A stale model bundle failed its format check, `load()` returned None, and the build wrote an empty
category for ninety-six percent of contracts with every step still green. None were hard to fix and
none were caught by a test, because nothing crashed: the pipeline did the wrong thing successfully.

Three things now stand against that.

**A promotion gate.** The design document promised since week one that "a regression past a stated
threshold fails the job and keeps the previous model", and until now nothing enforced it: every run
overwrote the serving model with whatever it had just fitted. `bidefy/models/gate.py` compares each
candidate with the model already serving and refuses one that lost more ground than that figure has
ever been seen to move between runs. The threshold is therefore measured rather than chosen -- it
comes from the same run-to-run spread the accuracy page publishes -- and the rule is sayable in a
line: block only when a figure moves further than it has ever moved. A refused candidate is filed in
`metrics.json`, the previous bundle keeps serving, and the accuracy page says so above every figure,
because a page describing a model nobody is served would be worse than useless.

**Invariants after the commit.** `tools/check_pipeline.py` asserts what each past incident violated,
stated as outcomes rather than code paths: some tender without a portal tag carries a model category,
every live tender has a band, every band is ordered, no estimate exceeds anything the archive has
ever awarded, and the accuracy page is byte-identical to what its writer produces right now. Because
they are outcomes, they catch causes nobody has thought of yet.

The ordering matters and is deliberate. These checks run *after* the crawl's data is committed and
*before* the D1 load. A check that ran earlier would pay for a failure with hours of crawling, which
is a worse trade than the failure; a check that ran later would let a run nobody can vouch for reach
the live database.

**CI that covers the whole repository.** It used to run `pytest` alone, so the Worker's tests and
both TypeScript projects were only checked by the deploy workflow, after merge. It now lints Python,
runs all three test suites with coverage against a floor, type-checks the Worker and the site, builds
the site, and asserts the generated-file invariant on every push.

**An alert, not a log line.** A failed workflow does send mail, but it says only that something
failed. A broken invariant now opens a GitHub issue carrying which invariant broke, what it printed
and a link to the run, and closes it again on the first run where they all hold. One issue is reused,
so a week of broken nights is one thread rather than fourteen, and a stale alert cannot sit open
teaching everyone to ignore it.

**A coverage floor.** Coverage was never measured, and measuring it found
`tools/write_accuracy_doc.py` at six percent -- 270 of 288 statements never executed -- while writing
the product's central artefact. Two of the seven findings in the last review were in that file, and
both would have printed a false claim on the page that exists to prove the numbers are trustworthy.
The least-tested file produced the most dangerous bugs. CI now fails below eighty percent, and the
two utilities a person runs by hand are excluded from the denominator with the reason stated rather
than padded with tests nobody would trust.

## What usage there is, and how it is counted

`/api/v1/usage` returns counts and timestamps, never a row that identifies anyone: endpoints,
push keys and contact details stay in their tables. It reports two kinds of number and keeps them
apart, because collapsing them would be the easiest lie on the site.

Subscribers, alerts delivered and access requests are **demand**, and they are zero. That is not a
fault and not a bug in the endpoint: the launch post has not been published and no one has been
told the product exists. A dashboard that printed three zeros without saying which kind of zero
they were would leave a reader guessing whether the pipeline was dead, so the command centre says
it in words.

Alert runs and the tenders each run examined are **liveness**, and they are real from the first
hour. The hourly cron reads every tender published since its watermark whether or not anyone is
subscribed, so a row lands every hour regardless. Each run is now written to `alert_runs`, which
makes it the only honest usage figure the product has before it has an audience, and the only
evidence the cron is alive at all. A failed write there is swallowed: bookkeeping must never cost
an alert.

The one number that cannot be produced honestly yet is engagement, because there is nobody to
engage. It arrives the day the launch post does.

## How much the published figures move, and why that is measured from git

`tools/metrics_stability.py` reads the run-to-run spread of every headline figure out of the history
of `models/metrics.json`, and the accuracy page publishes it. The alternative was to retrain the
award model many times to estimate its own spread, which would cost an hour and would still miss
the larger source: the award model takes the category as a feature, so it inherits the classifier's
refit every night. Reading the real history catches every source at once.

Two operational consequences. The nightly checkout uses `fetch-depth: 120`, because a shallow clone
would see one training run and report a noise floor of zero, which is the flattering direction. And
the tool withholds the whole table below five runs rather than publish a floor measured over two,
since understating the floor is exactly how a change gets read as a result.

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
