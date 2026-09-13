# The system

## One pipeline, nightly

1. **Crawl.** One request per second against the portal's two public list endpoints, 200 rows a page, checkpointed after every flush, resumed across nights until the index is complete, then a daily delta that stops at the first page with nothing new.
2. **Compact.** Small Parquet parts merge into one file once twenty accumulate, so the repository stays a few hundred files rather than thousands.
3. **Resolve.** Bidder names are normalised (prefixes such as M/S dropped, punctuation stripped, Bangla combining marks kept), blocked on their first long token, and compared with character n-gram TF-IDF. Pairs at or above 0.92 merge, pairs from 0.80 to 0.92 wait in a review file for a human decision, and every entity gets a stable id from its canonical name.
4. **Classify.** A sample of detail pages supplies the portal's own category tags, mapped to fifteen Bidefy categories as weak labels. A TF-IDF and logistic regression model predicts the category of every title and defers below a confidence threshold. Metrics are reported on the acted-on predictions with the deferral rate beside them.
5. **Load.** The last twelve months and every live tender go to Cloudflare D1 in statements under 100 KB, capped at 45,000 rows per run so two runs a day stay under the free tier's 100,000 writes.
6. **Serve.** A Worker answers the API from D1. The site on Vercel renders on the server from that API with short revalidation, so pages are fast and shareable.
7. **Alert.** Every hour the Worker takes tenders newer than its watermark, matches them against each subscription's filters, sends web push through the Web Crypto push protocol, records what it sent so nothing repeats, and deletes endpoints that answer 404 or 410.

## The deferral principle

A classifier that must answer every time is wrong more often than one allowed to say "not sure". Bidefy publishes accuracy only for the predictions it acts on, and publishes the deferral rate next to it, because a high accuracy with a hidden deferral rate is meaningless. The same rule will govern the award-value model: an interval and a coverage figure, never a single number.

## Model metrics at launch (v0.1, 13 September 2026)

| Figure | Value |
|---|---|
| Detail pages sampled for labels | 1,427 |
| Labels from portal tags | 1,157 |
| Training titles including title-keyword labels | 4,600 |
| Held-out test titles | 1,151 |
| Classes | 15 |
| Accuracy on acted-on predictions | 0.906 |
| Deferral rate | 0.158 |
| Macro F1 over all predictions | 0.843 |
| Confidence threshold | 0.55 |

Read the first two rows together: 90.6 percent of the categories Bidefy commits to are right, and it declines to commit on 15.8 percent of tenders. The command centre shows the live figures from `models/metrics.json` after every nightly retrain.

## Budgets that shape the design

| Budget | Value | Consequence |
|---|---|---|
| Portal politeness | 1 request per second, one session | Full index takes an hour from Dhaka, several nights from a US runner |
| D1 writes | 100,000 a day, and every index entry counts as a write | Budget kept in writes, not rows: a tender row costs five. Awards never go in as rows; bidder and entity profiles carry JSON aggregates. 80,000 writes a day across both runs, tracked in the watermark |
| D1 statement size | about 100 KB | Byte-aware batching, roughly 150 rows per statement |
| GitHub Actions | 6 hours per job | 300-minute crawl budget, checkpoint and resume |
| Push per subscription | 20 per hourly run | A noisy filter cannot flood a phone |

## What is not built, on purpose

No WhatsApp, no payments, no fraud verdicts, no mirror of raw notices, no losing-bid data because the portal does not publish it.
