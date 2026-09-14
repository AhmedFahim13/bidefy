# The system

## One pipeline, nightly

1. **Crawl.** One request per second against the portal's two public list endpoints, 200 rows a page, checkpointed after every flush, resumed across nights until the index is complete, then a daily delta that stops at the first page with nothing new.
2. **Compact.** Small Parquet parts merge into one file once twenty accumulate, so the repository stays a few hundred files rather than thousands.
3. **Resolve.** Bidder names are normalised (prefixes such as M/S dropped, punctuation stripped, Bangla combining marks kept), blocked on their first long token, and compared with character n-gram TF-IDF. Pairs at or above 0.92 merge, pairs from 0.80 to 0.92 wait in a review file for a human decision, and every entity gets a stable id from its canonical name.
4. **Fetch details.** Every open tender's detail page is fetched, one a second. It carries the portal's own category tags and the refundable tender security, which are the two most valuable fields on the whole portal and appear nowhere in the list pages.
5. **Classify and price.** The category is read from those tags where present, and predicted only where it is not. The award band is built from the security where the notice publishes one, and from the entity's history otherwise. Both may decline.
6. **Load.** The last twelve months and every live tender go to Cloudflare D1 in statements under 100 KB, budgeted in row writes rather than rows, because every index entry counts as one.
7. **Serve.** A Worker answers the API from D1. The site on Vercel renders on the server from that API with short revalidation, so pages are fast and shareable.
8. **Alert.** Every hour the Worker takes tenders newer than its watermark, matches them against each subscription's filters, sends web push through the Web Crypto push protocol, records what it sent so nothing repeats, and deletes endpoints that answer 404 or 410.

## The deferral principle

A classifier that must answer every time is wrong more often than one allowed to say "not sure". Bidefy publishes accuracy only for the predictions it acts on, and publishes the deferral rate next to it, because a high accuracy with a hidden deferral rate is meaningless. The award-value model follows the same rule: a band with its measured coverage, never a single number, and a decline when the band would be too wide to act on.

## How well the models work

Every current figure lives on its own page, [What Bidefy gets right, and how often](05-accuracy.md), which is rewritten by each training run so it cannot drift from the model it describes. The short version:

- An award band built from the tender security published in the notice lands within about 8 percent of the real award value. A band built from the entity's history alone is far looser.
- A tender's category is read from the portal's own tags for every live tender, so on the live site it is not a prediction at all. The classifier only covers the archive.
- Both models may decline, and the deferral rate is always printed beside the accuracy.
- The history band is two quantile models with a conformal pad, not one estimate stretched by a difficulty score. That change alone raised coverage and cut the share of tenders declined, without moving any threshold. [What was tried, and what the measurements said](06-experiments.md) has the before and after.

## Two lessons worth keeping

**A model must not be scored on a rule you wrote.** The category model once trained partly on labels produced by a keyword rule inside Bidefy, and was then scored on a test set containing those same labels. It looked accurate. Measured against the portal's own tags it was not, and feeding it twenty thousand keyword labels drove real accuracy from 89.8 percent to 55.4 percent. The labels were removed.

**Read the answer before predicting it.** The portal publishes category tags on each tender's detail page, and a tender security that is a fixed share of the buyer's own cost estimate. Fetching those pages turned the category from a prediction into a lookup, and cut the award band from roughly eleven times wide to about one and a half. Most of the accuracy came from collecting better evidence, not from a better model.

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
