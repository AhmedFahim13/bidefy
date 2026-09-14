# What Bidefy gets right, and how often

Every figure here is measured on data the model was not trained on, and this page is written by the training run itself, so it cannot drift from the model it describes.

Two rules govern everything below. A model may decline, and when it declines that is reported next to its accuracy, because an accuracy figure without its deferral rate is not a measurement. And a prediction is only scored against evidence the model could not have seen: the portal's own records, never a rule Bidefy wrote.

## Award value

The history route is trained on 546,033 awards, calibrated on 327,620 out-of-sample residuals, and scored on the 136,579 most recent awards, everything signed on or after 2025-06-24. Every award it is scored on is later in time than every award used to fit or calibrate it, so this is a forecast, not a fit.

A tender notice publishes a refundable tender security. Buyers set it as a fixed share of a cost estimate they do not publish, and awards land near that estimate, so where a security exists it pins the value far more tightly than history can.

The two routes are measured on two different windows, and are never averaged into one headline. The archive of awards reaches back years, but detail pages have only been fetched for roughly the last year, so every published security on record is recent. Split the whole archive by date and all of them land after the cut, leaving the security multiplier nothing to learn from. So that route is given its own split, at eighty percent of the securities by date, fitted on the earlier ones and scored on the later ones. Both windows are strictly forward-looking.

| | From the tender security | From entity history |
|---|---|---|
| Awards scored | 423 | 105,039 |
| Fitted on | 1,673 earlier securities | 546,033 earlier awards |
| Scored on awards signed from | 2026-08-04 | 2025-06-24 |
| Median error of the central estimate | 8.7 percent | 37.9 percent |
| Share of awards inside the band | 79.7 percent | 78.6 percent |
| Typical band, high over low | 1.42x | 5.09x |

Of the 2,096 awards in the archive whose notice published a security, that is every one the route could be scored on without fitting and testing on the same rows.

### What a bidder actually meets

Of the tenders open right now, 80.0 percent publish a security and take the precise route; the rest fall to history. The archive is a poor guide to that split, because its detail pages were mostly never fetched, so a security looks absent there when it was only uncollected. Weighting the two measured routes by the split the site actually serves:

| Route | Share of open tenders | Median error | Typical band |
|---|---|---|---|
| From the tender security | 80.0 percent | 8.7 percent | 1.42x |
| From entity history | 20.0 percent | 37.9 percent | 5.09x |

Four tenders in five get the precise answer. That is a property of what the portal publishes, not of the model, and it is the single most valuable thing found in this project. Nothing here is an average of the two rows: each is measured on its own held-out window and reported as itself.

Taking the test window exactly as crawled, with whatever mix of routes it happens to contain, the median error is 37.0 percent and the typical band is 5.02x wide. For scale, the spread between the 10th and 90th percentile of all awards is 56x, which is the band someone would quote knowing nothing at all. Simply guessing the median award for every tender gives a median error of 79.5 percent.

### The history route is not one number

Open tendering is the hardest method to price and the one the history route is mostly asked about, because a large open tender is exactly the kind that publishes no security. Quoting a single history figure would hide that, so here is each method on its own.

| Method | Tenders answered | Median error | Inside the band | Typical band | Declined |
|---|---|---|---|---|---|
| LTM | 53,453 | 32.2 percent | 81.2 percent | 4.26x | 6.3 percent |
| OTM | 40,133 | 45.3 percent | 75.4 percent | 6.19x | 31.4 percent |
| RFQU | 6,132 | 43.0 percent | 78.9 percent | 6.26x | 30.1 percent |
| RFQ | 4,299 | 42.9 percent | 77.3 percent | 5.3x | 45.9 percent |
| DPM | 446 | 69.5 percent | 71.5 percent | 7.16x | 28.9 percent |
| RFQL | 403 | 46.0 percent | 86.4 percent | 6.55x | 53.1 percent |
| OSTETM | 129 | 57.0 percent | 67.4 percent | 9.31x | 76.3 percent |

Bidefy declines when a band would be too wide to act on. Where that line is drawn is a product decision, not a statistical one, so here is the whole trade:

| Widest band shown | Tenders declined |
|---|---|
| 4x | 73.6 percent |
| 6x | 48.8 percent |
| 8x | 32.0 percent |
| 12x | 15.8 percent |
| 20x | 5.1 percent |

## Category

A tender's category is read from the portal's own tags wherever Bidefy has fetched that tender's detail page. The model below exists only to cover tenders whose detail page has not been fetched, mostly older archived ones.

Of the 3,405 tenders open right now, 85.2 percent take their category straight from the portal. For those the category is not a prediction at all, and nothing is declined.

Trained and scored on 6,640 tenders across 15 categories, cross-validated on portal category tags only, entity priors from the training fold.

| Measure | Value |
|---|---|
| Accuracy on the predictions it commits to | 93.0 percent |
| Share of tenders it declines | 44.7 percent |
| Accuracy if forced to answer every time | 75.9 percent |
| Macro F1 across categories | 0.639 |
| Deferral needed to reach 93 percent | 44.7 percent |
| Deferral needed to reach 95 percent | 52.2 percent |

This model is not deterministic. Run the same cross-validation again, on the same data with the same seed, and the share it declines moves by up to 0.5 percent and its macro F1 by 0.016. That is the floor below which a change to this model cannot be distinguished from chance, and it is published here because a figure quoted without it invites reading an improvement into noise. The numbers above pool 3 runs, which is why they are steadier than any one of them.

## What would move these numbers

The award band is limited by what a notice says. The title carries the item but rarely the quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page of every live tender is what unlocks the security route, and that is now part of the nightly run. The category model is limited by labelled examples, and every detail page fetched adds one.

An earlier version of the category model also trained on labels produced by a keyword rule Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making the published figure look better, because the model was partly being scored on the rule it had been taught to copy.
