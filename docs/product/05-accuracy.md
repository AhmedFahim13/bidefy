# What Bidefy gets right, and how often

Every figure here is measured on data the model was not trained on, and this page is written by the training run itself, so it cannot drift from the model it describes.

Two rules govern everything below. A model may decline, and when it declines that is reported next to its accuracy, because an accuracy figure without its deferral rate is not a measurement. And a prediction is only scored against evidence the model could not have seen: the portal's own records, never a rule Bidefy wrote.

## Award value

Trained on 167,959 awards, calibrated on 100,776 out-of-sample residuals, tested on the 42,585 most recent awards (everything signed on or after 2026-05-11). The test awards are later in time than every award used to fit or calibrate, so this is a forecast, not a fit.

A tender notice publishes a refundable tender security. Buyers set it as a fixed share of a cost estimate they do not publish, and awards land near that estimate, so where a security exists it pins the value far more tightly than history can.

| | From the tender security | From entity history |
|---|---|---|
| Tenders in the test set | 1,586 | 29,107 |
| Median error of the central estimate | 8.4 percent | 36.3 percent |
| Share of awards inside the band | 83.9 percent | 76.7 percent |
| Typical band, high over low | 1.46x | 4.77x |

### What a bidder actually meets

Of the tenders open right now, 80.0 percent publish a security and take the precise route. The historical test window looks nothing like that, because its detail pages have mostly never been fetched, so a security appears absent there when it was only uncollected. Resampling the test awards to today's mix of routes gives the figures a bidder should expect:

| Measure | Value |
|---|---|
| Median error of the central estimate | 9.9 percent |
| Share of awards inside the band | 82.8 percent |
| Typical band, high over low | 1.46x |

This is a projection onto a different population, not a fourth measurement. Every number in it comes from held-out awards; only the proportions are changed, and they are changed to match what the site serves.

Across the test window as crawled, the median error is 33.9 percent and the typical band is 4.6x wide. For scale, the spread between the 10th and 90th percentile of all awards is 59x, which is the band someone would quote knowing nothing at all. Simply guessing the median award for every tender gives a median error of 78.0 percent.

Bidefy declines when a band would be too wide to act on. Where that line is drawn is a product decision, not a statistical one, so here is the whole trade:

| Widest band shown | Tenders declined |
|---|---|
| 4x | 70.8 percent |
| 6x | 49.3 percent |
| 8x | 37.6 percent |
| 12x | 25.1 percent |
| 20x | 13.7 percent |

## Category

A tender's category is read from the portal's own tags wherever Bidefy has fetched that tender's detail page. The model below exists only to cover tenders whose detail page has not been fetched, mostly older archived ones.

Trained and scored on 5,470 tenders across 15 categories, cross-validated on portal category tags only, entity priors from the training fold.

| Measure | Value |
|---|---|
| Accuracy on the predictions it commits to | 93.0 percent |
| Share of tenders it declines | 43.1 percent |
| Accuracy if forced to answer every time | 76.3 percent |
| Macro F1 across categories | 0.628 |
| Deferral needed to reach 93 percent | 43.1 percent |
| Deferral needed to reach 95 percent | 49.4 percent |

## What would move these numbers

The award band is limited by what a notice says. The title carries the item but rarely the quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page of every live tender is what unlocks the security route, and that is now part of the nightly run. The category model is limited by labelled examples, and every detail page fetched adds one.

An earlier version of the category model also trained on labels produced by a keyword rule Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making the published figure look better, because the model was partly being scored on the rule it had been taught to copy.
