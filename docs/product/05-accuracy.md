# What Bidefy gets right, and how often

Every figure here is measured on data the model was not trained on, and this page is written by the training run itself, so it cannot drift from the model it describes.

Two rules govern everything below. A model may decline, and when it declines that is reported next to its accuracy, because an accuracy figure without its deferral rate is not a measurement. And a prediction is only scored against evidence the model could not have seen: the portal's own records, never a rule Bidefy wrote.

## Award value

The history route is trained on 703,083 awards, calibrated on 421,850 out-of-sample residuals, and scored on the 176,102 most recent awards, everything signed on or after 2025-03-24. Every award it is scored on is later in time than every award used to fit or calibrate it, so this is a forecast, not a fit.

A tender notice publishes a refundable tender security. Buyers set it as a fixed share of a cost estimate they do not publish, and awards land near that estimate, so where a security exists it pins the value far more tightly than history can.

The two routes are measured on two different windows, and are never averaged into one headline. The archive of awards reaches back years, but detail pages have only been fetched for roughly the last year, so every published security on record is recent. Split the whole archive by date and all of them land after the cut, leaving the security multiplier nothing to learn from. So that route is given its own split, at eighty percent of the securities by date, fitted on the earlier ones and scored on the later ones. Both windows are strictly forward-looking.

| | From the tender security | From entity history |
|---|---|---|
| Awards scored | 5,248 | 127,196 |
| Fitted on | 15,574 earlier securities | 703,083 earlier awards |
| Scored on awards signed from | 2026-06-18 | 2025-03-24 |
| Median error of the central estimate | 7.7 percent | 38.2 percent |
| Share of awards inside the band | 76.4 percent | 77.5 percent |
| Typical band, high over low | 1.36x | 4.94x |

Of the 26,051 awards in the archive whose notice published a usable security, that is every one the route could be scored on without fitting and testing on the same rows. A further 70 published a figure that cannot be true -- one 66 lakh award lists a security of 804 crore -- and those are dropped from fitting, calibration and scoring alike, because a typo left in the calibration slice would stretch the band on the strength of nothing.

### A band ages

The share buyers ask for drifts upward, and the spread of awards around it has widened month by month. So a band set in June covers June better than it covers September. The model retrains every night, which means the band a live tender meets is a day or two old, never months. Coverage is therefore reported against how stale the band was when the award landed.

| Band was this old | Awards | Inside the band |
|---|---|---|
| within a week | 694 | 82.7 percent |
| one to three weeks | 939 | 77.5 percent |
| three to six weeks | 1,232 | 75.9 percent |
| over six weeks | 2,383 | 74.4 percent |

The first row is the one the product runs at. The last is what the same band is worth months after it was set, and it is the figure in the table above, because measuring against the whole window is the conservative choice.

### What a bidder actually meets

Of the tenders open right now, 84.7 percent publish a security and take the precise route; the rest fall to history. The archive is a poor guide to that split, because its detail pages were mostly never fetched, so a security looks absent there when it was only uncollected. Weighting the two measured routes by the split the site actually serves:

| Route | Share of open tenders | Median error | Typical band |
|---|---|---|---|
| From the tender security | 84.7 percent | 7.7 percent | 1.36x |
| From entity history | 15.3 percent | 38.2 percent | 4.94x |

Four tenders in five get the precise answer. That is a property of what the portal publishes, not of the model, and it is the single most valuable thing found in this project. Nothing here is an average of the two rows: each is measured on its own held-out window and reported as itself.

### Counted per tender, and counted per taka

Every coverage figure above counts each tender once. A bidder pricing a three crore job is not one vote among small purchases, so the same coverage is also reported with each award weighted by its size. The two are different numbers and the gap between them is itself a measurement.

| | Per tender | Per taka estimated | Per taka awarded |
|---|---|---|---|
| From the tender security | 76.4 percent | 72.0 percent | 67.6 percent |
| From entity history | 77.5 percent | 76.1 percent | 62.5 percent |

Coverage per taka awarded is the lowest of the three, and the reason is arithmetic rather than a defect. An award that escapes its band mostly escapes upward -- 92.0 percent of the taka that fell outside a band fell above its ceiling -- so a miss carries more money than a hit does, and weighting by the award that landed gives those misses more of the total. Weighting by the estimate instead, which is the only size anyone knows before the award, the figure sits close to the per-tender one. The middle column is what a bidder can rely on in advance; the right-hand column is what a year of tenders added up to afterwards.

Bands are cut on the model's own estimate, because that is what a reader has before the award. Cutting them on the award that landed would answer a different question and answer it wrongly: the largest actual awards are, by the arithmetic of selection, the ones the model guessed low on, so that cut makes any honest model look as though it collapses on large tenders.

| Bidefy's estimate | Tenders | Median error | Inside the band | Above the ceiling | Below the floor |
|---|---|---|---|---|---|
| 0.2 to 3.76 lakh | 25,402 | 38.0 percent | 78.4 percent | 15.0 percent | 6.6 percent |
| 3.77 to 7.07 lakh | 25,421 | 39.6 percent | 78.5 percent | 13.6 percent | 8.0 percent |
| 7.08 to 12.29 lakh | 25,480 | 35.4 percent | 78.2 percent | 12.4 percent | 9.4 percent |
| 12.3 to 31.82 lakh | 25,449 | 37.9 percent | 76.1 percent | 9.7 percent | 14.2 percent |
| 31.83 to 3,338.74 lakh | 25,444 | 40.3 percent | 76.2 percent | 10.5 percent | 13.2 percent |

Coverage runs between 76.1 percent and 78.5 percent across those bands, so the route does not fall apart on the large end. What changes is the direction of the misses. In the lowest band 15.0 percent of awards overtook the ceiling and 6.6 percent fell through the floor; in the highest band it is 10.5 percent and 13.2 percent. The median award lands at 1.16 times the estimate in the lowest band and 0.97 times in the highest. A central estimate pulled toward the middle by weak features looks exactly like that, and the feature it lacks is the quantity, which a notice states only rarely.

The security route is steadier still in what it promises: its band is 1.36x wide in every one of the five size bands, and its median error runs 6.8 percent to 8.5 percent across them. The relationship it uses is a multiple, so its error is relative by construction and does not grow with the size of the job. Its coverage moves more, 73.6 percent to 79.2 percent, but the smallest band holds only 1,031 awards, where the sampling error on a coverage figure is already well over a point, so that spread is not evidence of anything.

Taking the test window exactly as crawled, with whatever mix of routes it happens to contain, the median error is 30.1 percent and the typical band is 4.31x wide. For scale, the spread between the 10th and 90th percentile of all awards is 5x, which is the band someone would quote knowing nothing at all. Simply guessing the median award for every tender gives a median error of 79.0 percent.

### The history route is not one number

Open tendering is the hardest method to price and the one the history route is mostly asked about, because a large open tender is exactly the kind that publishes no security. Quoting a single history figure would hide that, so here is each method on its own.

| Method | Tenders answered | Median error | Inside the band | Typical band | Declined |
|---|---|---|---|---|---|
| LTM | 74,449 | 33.4 percent | 79.1 percent | 4.19x | 3.4 percent |
| OTM | 37,563 | 46.4 percent | 75.7 percent | 6.6x | 28.9 percent |
| RFQU | 7,734 | 45.9 percent | 72.7 percent | 5.85x | 18.4 percent |
| RFQ | 6,276 | 43.0 percent | 75.5 percent | 5.41x | 24.4 percent |
| RFQL | 656 | 46.5 percent | 80.3 percent | 6.67x | 28.5 percent |
| DPM | 389 | 58.7 percent | 73.8 percent | 8.67x | 40.0 percent |

Bidefy declines when a band would be too wide to act on. Where that line is drawn is a product decision, not a statistical one, so here is the whole trade:

| Widest band shown | Tenders declined |
|---|---|
| 4x | 60.4 percent |
| 6x | 38.1 percent |
| 8x | 23.9 percent |
| 12x | 11.1 percent |
| 20x | 3.6 percent |

## Category

Categories are read from the portal's CPV procurement codes, through the official code hierarchy. Most buyers tick the whole construction division rather than a kind of work, so construction is one category, and roads, buildings or water is shown only where the buyer's codes state it. The model below covers tenders whose detail page has not been fetched, mostly older archived ones.

Of the 47,823 tenders with codes on record, 81.0 percent carry codes that identify a sector. The rest were ticked so broadly that the codes say nothing about what is being bought. There is no ground truth to score those against, so they are not in the figures below, and that has to be said before the figures are read. An earlier model scored all of them against keyword labels across fifteen categories and declined 38.5 percent at the same 93 percent accuracy. The experiment log measures how much of the difference is this change of scope rather than a better model: most of it.

Of the 6,199 tenders open right now, 82.6 percent take their category straight from the portal. For those the category is not a prediction at all, and nothing is declined.

Trained and scored on 38,734 tenders across 13 categories, cross-validated against the sector the portal's CPV codes identify, on tenders whose codes identify one, with buyer priors from the training fold only.

| Measure | Value |
|---|---|
| Accuracy on the predictions it commits to | 93.0 percent |
| Share of tenders it declines | 13.8 percent |
| Accuracy if forced to answer every time | 86.8 percent |
| Macro F1 across categories | 0.71 |
| Deferral needed to reach 93 percent | 13.8 percent |
| Deferral needed to reach 95 percent | 20.1 percent |

This model is not deterministic. Run the same cross-validation again, on the same data with the same seed, and the share it declines moves by up to 0.2 percent and its macro F1 by 0.003. That is the floor below which a change to this model cannot be distinguished from chance, and it is published here because a figure quoted without it invites reading an improvement into noise. The numbers above pool 3 runs, which is why they are steadier than any one of them.

## What would move these numbers

The award band is limited by what a notice says. The title carries the item but rarely the quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page of every live tender is what unlocks the security route, and that is now part of the nightly run. The category model is limited by labelled examples, and every detail page fetched adds one.

An earlier version of the category model also trained on labels produced by a keyword rule Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making the published figure look better, because the model was partly being scored on the rule it had been taught to copy.
