# What Bidefy gets right, and how often

Every figure here is measured on data the model was not trained on, and this page is written by the training run itself, so it cannot drift from the model it describes.

Two rules govern everything below. A model may decline, and when it declines that is reported next to its accuracy, because an accuracy figure without its deferral rate is not a measurement. And a prediction is only scored against evidence the model could not have seen: the portal's own records, never a rule Bidefy wrote.

## Award value

Trained on 168,435 awards, calibrated on 101,061 out-of-sample residuals, tested on the 42,109 most recent awards (everything signed on or after 2026-05-11). The test awards are later in time than every award used to fit or calibrate, so this is a forecast, not a fit.

A tender notice publishes a refundable tender security. Buyers set it as a fixed share of a cost estimate they do not publish, and awards land near that estimate, so where a security exists it pins the value far more tightly than history can.

| | From the tender security | From entity history |
|---|---|---|
| Tenders in the test set | 303 | 23,974 |
| Median error of the central estimate | 7.7 percent | 34.2 percent |
| Share of awards inside the band | 84.2 percent | 76.7 percent |
| Typical band, high over low | 1.47x | 4.42x |

Across both routes the median error is 33.7 percent and the typical band is 4.39x wide. For scale, the spread between the 10th and 90th percentile of all awards is 59x, which is the band someone would quote knowing nothing at all. Simply guessing the median award for every tender gives a median error of 78.0 percent.

Bidefy declines when a band would be too wide to act on. Where that line is drawn is a product decision, not a statistical one, so here is the whole trade:

| Widest band shown | Tenders declined |
|---|---|
| 4x | 75.3 percent |
| 6x | 54.4 percent |
| 8x | 40.6 percent |
| 12x | 26.5 percent |
| 20x | 13.5 percent |

## Category

A tender's category is read from the portal's own tags wherever Bidefy has fetched that tender's detail page. The model below exists only to cover tenders whose detail page has not been fetched, mostly older archived ones.

Trained and scored on 1,942 tenders across 14 categories, cross-validated on portal category tags only.

| Measure | Value |
|---|---|
| Accuracy on the predictions it commits to | 89.8 percent |
| Share of tenders it declines | 37.1 percent |
| Accuracy if forced to answer every time | 74.1 percent |
| Macro F1 across categories | 0.564 |
| Deferral needed to reach 93 percent | 52.1 percent |
| Deferral needed to reach 95 percent | 58.2 percent |

Categories held back for want of examples: water_sanitation. They return once the detail crawl has collected enough of them.

## What would move these numbers

The award band is limited by what a notice says. The title carries the item but rarely the quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page of every live tender is what unlocks the security route, and that is now part of the nightly run. The category model is limited by labelled examples, and every detail page fetched adds one.

An earlier version of the category model also trained on labels produced by a keyword rule Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making the published figure look better, because the model was partly being scored on the rule it had been taught to copy.
