# What Bidefy gets right, and how often

Every figure here is measured on data the model was not trained on, and this page is written by the training run itself, so it cannot drift from the model it describes.

Two rules govern everything below. A model may decline, and when it declines that is reported next to its accuracy, because an accuracy figure without its deferral rate is not a measurement. And a prediction is only scored against evidence the model could not have seen: the portal's own records, never a rule Bidefy wrote.

## Award value

The history route is trained on 701,561 awards, calibrated on 420,937 out-of-sample residuals, and scored on the 175,816 most recent awards, everything signed on or after 2025-03-19. Every award it is scored on is later in time than every award used to fit or calibrate it, so this is a forecast, not a fit.

A tender notice publishes a refundable tender security. Buyers set it as a fixed share of a cost estimate they do not publish, and awards land near that estimate, so where a security exists it pins the value far more tightly than history can.

The two routes are measured on two different windows, and are never averaged into one headline. The archive of awards reaches back years, but detail pages have only been fetched for roughly the last year, so every published security on record is recent. Split the whole archive by date and all of them land after the cut, leaving the security multiplier nothing to learn from. So that route is given its own split, at eighty percent of the securities by date, fitted on the earlier ones and scored on the later ones. Both windows are strictly forward-looking.

| | From the tender security | From entity history |
|---|---|---|
| Awards scored | 3,430 | 128,961 |
| Fitted on | 10,111 earlier securities | 701,561 earlier awards |
| Scored on awards signed from | 2026-06-18 | 2025-03-19 |
| Median error of the central estimate | 7.7 percent | 38.3 percent |
| Share of awards inside the band | 76.9 percent | 77.4 percent |
| Typical band, high over low | 1.36x | 4.94x |

Of the 16,853 awards in the archive whose notice published a security, that is every one the route could be scored on without fitting and testing on the same rows.

### A band ages

The share buyers ask for drifts upward, and the spread of awards around it has widened month by month. So a band set in June covers June better than it covers September. The model retrains every night, which means the band a live tender meets is a day or two old, never months. Coverage is therefore reported against how stale the band was when the award landed.

| Band was this old | Awards | Inside the band |
|---|---|---|
| within a week | 472 | 81.8 percent |
| one to three weeks | 655 | 75.7 percent |
| three to six weeks | 845 | 77.3 percent |
| over six weeks | 1,458 | 75.6 percent |

The first row is the one the product runs at. The last is what the same band is worth months after it was set, and it is the figure in the table above, because measuring against the whole window is the conservative choice.

### What a bidder actually meets

Of the tenders open right now, 84.7 percent publish a security and take the precise route; the rest fall to history. The archive is a poor guide to that split, because its detail pages were mostly never fetched, so a security looks absent there when it was only uncollected. Weighting the two measured routes by the split the site actually serves:

| Route | Share of open tenders | Median error | Typical band |
|---|---|---|---|
| From the tender security | 84.7 percent | 7.7 percent | 1.36x |
| From entity history | 15.3 percent | 38.3 percent | 4.94x |

Four tenders in five get the precise answer. That is a property of what the portal publishes, not of the model, and it is the single most valuable thing found in this project. Nothing here is an average of the two rows: each is measured on its own held-out window and reported as itself.

Taking the test window exactly as crawled, with whatever mix of routes it happens to contain, the median error is 33.0 percent and the typical band is 4.52x wide. For scale, the spread between the 10th and 90th percentile of all awards is 48x, which is the band someone would quote knowing nothing at all. Simply guessing the median award for every tender gives a median error of 78.3 percent.

### The history route is not one number

Open tendering is the hardest method to price and the one the history route is mostly asked about, because a large open tender is exactly the kind that publishes no security. Quoting a single history figure would hide that, so here is each method on its own.

| Method | Tenders answered | Median error | Inside the band | Typical band | Declined |
|---|---|---|---|---|---|
| LTM | 73,410 | 33.4 percent | 79.5 percent | 4.2x | 5.0 percent |
| OTM | 42,901 | 46.0 percent | 74.8 percent | 6.24x | 30.8 percent |
| RFQU | 6,762 | 46.0 percent | 74.6 percent | 6.27x | 27.6 percent |
| RFQ | 4,791 | 43.0 percent | 74.3 percent | 5.1x | 40.8 percent |
| RFQL | 512 | 42.1 percent | 79.9 percent | 6.02x | 42.1 percent |
| DPM | 465 | 56.9 percent | 68.0 percent | 7.57x | 26.9 percent |

Bidefy declines when a band would be too wide to act on. Where that line is drawn is a product decision, not a statistical one, so here is the whole trade:

| Widest band shown | Tenders declined |
|---|---|
| 4x | 64.6 percent |
| 6x | 41.5 percent |
| 8x | 25.9 percent |
| 12x | 12.0 percent |
| 20x | 4.0 percent |

## Category

Categories are read from the portal's CPV procurement codes, through the official code hierarchy. Most buyers tick the whole construction division rather than a kind of work, so construction is one category, and roads, buildings or water is shown only where the buyer's codes state it. The model below covers tenders whose detail page has not been fetched, mostly older archived ones.

Of the 32,238 tenders with codes on record, 80.7 percent carry codes that identify a sector. The rest were ticked so broadly that the codes say nothing about what is being bought. There is no ground truth to score those against, so they are not in the figures below, and that has to be said before the figures are read. An earlier model scored all of them against keyword labels across fifteen categories and declined 38.5 percent at the same 93 percent accuracy. The experiment log measures how much of the difference is this change of scope rather than a better model: most of it.

Of the 4,167 tenders open right now, 90.2 percent take their category straight from the portal. For those the category is not a prediction at all, and nothing is declined.

Trained and scored on 26,016 tenders across 13 categories, cross-validated against the sector the portal's CPV codes identify, on tenders whose codes identify one, with buyer priors from the training fold only.

| Measure | Value |
|---|---|
| Accuracy on the predictions it commits to | 93.0 percent |
| Share of tenders it declines | 16.0 percent |
| Accuracy if forced to answer every time | 85.8 percent |
| Macro F1 across categories | 0.695 |
| Deferral needed to reach 93 percent | 16.0 percent |
| Deferral needed to reach 95 percent | 22.3 percent |

This model is not deterministic. Run the same cross-validation again, on the same data with the same seed, and the share it declines moves by up to 0.6 percent and its macro F1 by 0.005. That is the floor below which a change to this model cannot be distinguished from chance, and it is published here because a figure quoted without it invites reading an improvement into noise. The numbers above pool 3 runs, which is why they are steadier than any one of them.

## What would move these numbers

The award band is limited by what a notice says. The title carries the item but rarely the quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page of every live tender is what unlocks the security route, and that is now part of the nightly run. The category model is limited by labelled examples, and every detail page fetched adds one.

An earlier version of the category model also trained on labels produced by a keyword rule Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making the published figure look better, because the model was partly being scored on the rule it had been taught to copy.
