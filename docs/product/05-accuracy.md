# What Bidefy gets right, and how often

Every figure here is measured on data the model was not trained on, and this page is written by the training run itself, so it cannot drift from the model it describes.

Two rules govern everything below. A model may decline, and when it declines that is reported next to its accuracy, because an accuracy figure without its deferral rate is not a measurement. And a prediction is only scored against evidence the model could not have seen: the portal's own records, never a rule Bidefy wrote.

## Award value

The history route is trained on 703,083 awards, calibrated on 421,850 out-of-sample residuals, and scored on the 176,562 most recent awards, everything signed on or after 2025-03-24. Every award it is scored on is later in time than every award used to fit or calibrate it, so this is a forecast, not a fit.

A tender notice publishes a refundable tender security. Buyers set it as a fixed share of a cost estimate they do not publish, and awards land near that estimate, so where a security exists it pins the value far more tightly than history can.

The two routes are measured on two different windows, and are never averaged into one headline. The archive of awards reaches back years, but detail pages have only been fetched for roughly the last year, so every published security on record is recent. Split the whole archive by date and all of them land after the cut, leaving the security multiplier nothing to learn from. So that route is given its own split, at eighty percent of the securities by date, fitted on the earlier ones and scored on the later ones. Both windows are strictly forward-looking.

| | From the tender security | From entity history |
|---|---|---|
| Awards scored | 6,433 | 123,824 |
| Fitted on | 19,063 earlier securities | 703,083 earlier awards |
| Scored on awards signed from | 2026-06-18 | 2025-03-24 |
| Median error of the central estimate | 7.7 percent | 38.1 percent |
| Share of awards inside the band | 75.8 percent | 78.4 percent |
| Typical band, high over low | 1.35x | 5.05x |

The history route's figures carry a bootstrapped 95 percent interval: coverage between 78.2 percent and 78.6 percent, median error between 37.9 percent and 38.3 percent. That is the interval from sampling alone, on this many awards, and it is the narrowest of the several ways these numbers move. The run-to-run figures further down are wider, and those are the ones to judge a change against.

Of the 32,059 awards in the archive whose notice published a usable security, that is every one the route could be scored on without fitting and testing on the same rows. A further 85 published a figure that cannot be true -- one 66 lakh award lists a security of 804 crore -- and those are dropped from fitting, calibration and scoring alike, because a typo left in the calibration slice would stretch the band on the strength of nothing.

### A band ages

The share buyers ask for drifts upward, and the spread of awards around it has widened month by month. So a band set in June covers June better than it covers September. The model retrains every night, which means the band a live tender meets is a day or two old, never months. Coverage is therefore reported against how stale the band was when the award landed.

| Band was this old | Awards | Inside the band |
|---|---|---|
| within a week | 828 | 81.8 percent |
| one to three weeks | 1,122 | 76.8 percent |
| three to six weeks | 1,496 | 76.5 percent |
| over six weeks | 2,987 | 73.4 percent |

The first row is the one the product runs at. The last is what the same band is worth months after it was set, and it is the figure in the table above, because measuring against the whole window is the conservative choice.

### What a bidder actually meets

Of the tenders open right now, 83.3 percent publish a security and take the precise route; the rest fall to history. The archive is a poor guide to that split, because its detail pages were mostly never fetched, so a security looks absent there when it was only uncollected. Weighting the two measured routes by the split the site actually serves:

| Route | Share of open tenders | Median error | Typical band |
|---|---|---|---|
| From the tender security | 83.3 percent | 7.7 percent | 1.35x |
| From entity history | 16.7 percent | 38.1 percent | 5.05x |

Four tenders in five get the precise answer. That is a property of what the portal publishes, not of the model, and it is the single most valuable thing found in this project. Nothing here is an average of the two rows: each is measured on its own held-out window and reported as itself.

### Counted per tender, and counted per taka

Every coverage figure above counts each tender once. A bidder pricing a three crore job is not one vote among small purchases, so the same coverage is also reported with each award weighted by its size. The two are different numbers and the gap between them is itself a measurement.

| | Per tender | Per taka estimated | Per taka awarded |
|---|---|---|---|
| From the tender security | 75.8 percent | 70.6 percent | 66.4 percent |
| From entity history | 78.4 percent | 76.0 percent | 62.9 percent |

Coverage per taka awarded is the lowest of the three, and the reason is arithmetic rather than a defect. An award that escapes its band mostly escapes upward -- 91.8 percent of the taka that fell outside a band fell above its ceiling -- so a miss carries more money than a hit does, and weighting by the award that landed gives those misses more of the total. Weighting by the estimate instead, which is the only size anyone knows before the award, the figure sits close to the per-tender one. The middle column is what a bidder can rely on in advance; the right-hand column is what a year of tenders added up to afterwards.

Bands are cut on the model's own estimate, because that is what a reader has before the award. Cutting them on the award that landed would answer a different question and answer it wrongly: the largest actual awards are, by the arithmetic of selection, the ones the model guessed low on, so that cut makes any honest model look as though it collapses on large tenders.

| Bidefy's estimate | Tenders | Median error | Inside the band | Above the ceiling | Below the floor |
|---|---|---|---|---|---|
| 0.14 to 3.75 lakh | 24,753 | 38.0 percent | 79.6 percent | 14.3 percent | 6.1 percent |
| 3.76 to 7.01 lakh | 24,738 | 39.8 percent | 79.5 percent | 13.0 percent | 7.6 percent |
| 7.02 to 12.14 lakh | 24,787 | 35.4 percent | 79.4 percent | 11.6 percent | 9.1 percent |
| 12.15 to 30.98 lakh | 24,775 | 37.8 percent | 77.1 percent | 9.1 percent | 13.8 percent |
| 30.99 to 3,347.17 lakh | 24,771 | 39.8 percent | 76.4 percent | 10.1 percent | 13.5 percent |

Coverage runs between 76.4 percent and 79.6 percent across those bands, so the route does not fall apart on the large end. What changes is the direction of the misses. In the lowest band 14.3 percent of awards overtook the ceiling and 6.1 percent fell through the floor; in the highest band it is 10.1 percent and 13.5 percent. The median award lands at 1.16 times the estimate in the lowest band and 0.97 times in the highest. A central estimate pulled toward the middle by weak features looks exactly like that, and the feature it lacks is the quantity, which a notice states only rarely.

The security route is steadier still in what it promises: its band is 1.35x wide in every one of the five size bands, and its median error runs 6.6 percent to 8.5 percent across them. The relationship it uses is a multiple, so its error is relative by construction and does not grow with the size of the job. Its coverage moves more, 72.3 percent to 79.1 percent, but the smallest band holds only 1,286 awards, where the sampling error on a coverage figure is already well over a point, so that spread is not evidence of anything.

Taking the test window exactly as crawled, with whatever mix of routes it happens to contain, the median error is 28.2 percent and the typical band is 4.28x wide. For scale, the spread between the 10th and 90th percentile of all awards is 5x, which is the band someone would quote knowing nothing at all. Simply guessing the median award for every tender gives a median error of 79.0 percent.

### The history route is not one number

Open tendering is the hardest method to price and the one the history route is mostly asked about, because a large open tender is exactly the kind that publishes no security. Quoting a single history figure would hide that, so here is each method on its own.

| Method | Tenders answered | Median error | Inside the band | Typical band | Declined |
|---|---|---|---|---|---|
| LTM | 73,925 | 33.6 percent | 80.7 percent | 4.39x | 4.3 percent |
| OTM | 34,710 | 46.5 percent | 74.7 percent | 6.42x | 26.2 percent |
| RFQU | 7,502 | 45.3 percent | 74.9 percent | 6.27x | 21.0 percent |
| RFQ | 6,408 | 42.8 percent | 76.2 percent | 5.61x | 23.2 percent |
| RFQL | 666 | 45.7 percent | 82.1 percent | 7.08x | 28.1 percent |
| DPM | 478 | 56.1 percent | 70.3 percent | 7.83x | 26.5 percent |

Bidefy declines when a band would be too wide to act on. Where that line is drawn is a product decision, not a statistical one, so here is the whole trade:

| Widest band shown | Tenders declined |
|---|---|
| 4x | 59.2 percent |
| 6x | 37.0 percent |
| 8x | 22.6 percent |
| 12x | 10.0 percent |
| 20x | 3.1 percent |

## Category

Categories are read from the portal's CPV procurement codes, through the official code hierarchy. Most buyers tick the whole construction division rather than a kind of work, so construction is one category, and roads, buildings or water is shown only where the buyer's codes state it. The model below covers tenders whose detail page has not been fetched, mostly older archived ones.

Of the 57,919 tenders with codes on record, 81.0 percent carry codes that identify a sector. The rest were ticked so broadly that the codes say nothing about what is being bought. There is no ground truth to score those against, so they are not in the figures below, and that has to be said before the figures are read. An earlier model scored all of them against keyword labels across fifteen categories and declined 38.5 percent at the same 93 percent accuracy. The experiment log measures how much of the difference is this change of scope rather than a better model: most of it.

Of the 6,827 tenders open right now, 83.0 percent take their category straight from the portal. For those the category is not a prediction at all, and nothing is declined.

Trained and scored on 46,895 tenders across 13 categories, cross-validated against the sector the portal's CPV codes identify, on tenders whose codes identify one, with buyer priors from the training fold only.

| Measure | Value |
|---|---|
| Accuracy on the predictions it commits to | 93.0 percent |
| Share of tenders it declines | 13.0 percent |
| Accuracy if forced to answer every time | 87.0 percent |
| Macro F1 across categories | 0.716 |
| Deferral needed to reach 93 percent | 13.0 percent |
| Deferral needed to reach 95 percent | 19.1 percent |

### The bar is chosen on the same rows it is scored on

The confidence bar is not picked by hand; it is set to deliver the target accuracy. But it is set on the same pooled cross-validated predictions the accuracy and deferral above are then read off, so those two figures are the best case by construction. This project has been caught by that shape of mistake twice already, so here it is measured rather than assumed. Splitting the tenders in half, choosing the bar on one half and scoring the other, both ways round, the model delivers 93.0 percent accuracy at 13.0 percent deferral.

Against a bar the scored rows did not help choose, the published accuracy is 0.0 percent conservative and the published deferral 0.0 percent optimistic. The pair above is kept as the headline because it is the pair the served model runs at, and this paragraph is what it costs to say so honestly.

### Where the sweet spot is, and what it depends on

A wrong category and a missing one are not equally bad. A wrong one hides a tender from the bidder who wanted it and shows it to one who did not; a declined one still reaches people through the keyword, ministry and status filters. How much worse the wrong one is has not been measured, and turning it into taka would mean multiplying three figures nobody has: whether a reader would have bid, whether they would have won, and on what margin. So it is left as a ratio and swept.

| A wrong answer costs this many silences | Deferral that minimises the total | Accuracy there |
|---|---|---|
| 1x | 0.0 percent | 87.1 percent |
| 2x | 5.9 percent | 90.1 percent |
| 3x | 15.1 percent | 93.7 percent |
| 5x | 24.6 percent | 96.3 percent |
| 10x | 34.6 percent | 98.1 percent |

The operating point above is where this table puts it for a ratio of 3, and that is the whole claim: not that the point is optimal, but over what range of a number nobody has measured it would be. Below that range the model should answer everything and let readers judge; above it, decline far more. Nothing here moved the operating point, and nothing here may: a threshold shifted to improve a published figure trades one number for another without the model getting any better.

This model is not deterministic. Run the same cross-validation again, on the same data with the same seed, and the share it declines moves by up to 0.4 percent and its macro F1 by 0.005. That is the floor below which a change to this model cannot be distinguished from chance, and it is published here because a figure quoted without it invites reading an improvement into noise. The numbers above pool 3 runs, which is why they are steadier than any one of them.

## How much these numbers move between runs

Both models retrain on every nightly run, and every run rewrites this page. So how much a figure moves when nothing has been changed can be read straight out of the repository's history rather than estimated from it. Below are the last 14 training runs, from 2026-09-20T23:59:42Z to 2026-09-27T08:33:17Z.

| Figure | Then | Now | Typical step between runs | Widest spread |
|---|---|---|---|---|
| Award band coverage, whole window | 78.1 percent | 79.2 percent | 0.2 percent | 1.2 percent |
| Coverage, history route | 77.5 percent | 78.4 percent | 0.3 percent | 1.0 percent |
| Median error, history route | 38.6 percent | 38.1 percent | 0.1 percent | 0.8 percent |
| Band width, history route | 5.03x | 5.05x | 0.02x | 0.16x |
| Coverage, security route | 76.7 percent | 75.8 percent | 0.3 percent | 1.5 percent |
| Median error, security route | 7.8 percent | 7.7 percent | 0.0 percent | 0.2 percent |
| Award deferral | 13.6 percent | 11.7 percent | 0.3 percent | 2.0 percent |
| Category accuracy | 93.0 percent | 93.0 percent | 0.0 percent | 0.0 percent |
| Category deferral | 15.5 percent | 13.4 percent | 0.2 percent | 2.5 percent |
| Category macro F1 | 0.704 | 0.711 | 0.002 | 0.013 |

This is the floor below which a change to either model cannot be told from the weather. The figures meant to hold still move by a few tenths of a point between runs and by up to 1.5 percent across the week, so a result smaller than that is not a result. Three sources are mixed together here and are not separated: each model's own randomness, the award model taking the category as a feature and so inheriting the classifier's refit, and the archive growing every night.

Some figures are not meant to hold still, and against that floor their movement is real. It was earned by the detail crawl collecting more of what each model needs, not by any change to a model:

- Award deferral: 13.6 percent to 11.7 percent, a move of 2.0 percent against a typical step of 0.3 percent.
- Category deferral: 15.5 percent to 13.4 percent, a move of 2.1 percent against a typical step of 0.2 percent.
- Category macro F1: 0.704 to 0.711, a move of 0.007 against a typical step of 0.002.

Category accuracy sits flat at zero, and that is the design rather than a triumph: it is what the confidence bar is set to deliver, so it holds still by construction and the deferral beside it is the figure actually being measured. A target met exactly, every run, is a dial and not a result.

## What would move these numbers

The award band is limited by what a notice says. The title carries the item but rarely the quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page of every live tender is what unlocks the security route, and that is now part of the nightly run. The category model is limited by labelled examples, and every detail page fetched adds one.

An earlier version of the category model also trained on labels produced by a keyword rule Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making the published figure look better, because the model was partly being scored on the rule it had been taught to copy.
