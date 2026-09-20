# What was tried, and what the measurements said

A model is only trustworthy if the things that did not work are written down beside the things
that did. Every row below is an experiment run on the real data, with the evaluation population
held fixed so the comparison is about the change and nothing else.

Two rules were applied throughout. No result counts if it came from moving a confidence
threshold or a band-width cutoff, because that trades one published number for another without
the model getting better. And no result counts if the change altered which tenders were being
scored, because a model can always look better by being asked easier questions.

## Award value

The award model answers with a band, and reports what share of real awards landed inside it.

Every comparison in this section was run on the same 210,544-award extract, so the arms differ only
by the change under test. The crawl has since more than tripled that archive, to 682,612 awards, and
the figures published on the accuracy page come from the full set. A number here will therefore not
match one there; what carries across is the direction and size of each change, not its level.

| Change | Median error | Inside the band | Band width | Declined | Kept |
|---|---|---|---|---|---|
| Band scaled by a predicted difficulty | 33.9 percent | 77.1 percent | 4.60x | 27.9 percent | replaced |
| Band calibrated per method **and** per size | 33.7 percent | 77.0 percent | 4.70x | 28.3 percent | no |
| Band calibrated per size alone | 34.7 percent | 77.1 percent | 4.95x | 25.2 percent | no |
| **Two quantile models, conformalised** | 34.8 percent | **79.6 percent** | 4.89x | **21.4 percent** | **yes** |

**Splitting the calibration by size did nothing.** The idea was that a small purchase and a large
one are not equally predictable, so one shared band serves neither. Measured, it moved coverage by
a tenth of a point and cost width. Rejected.

**Replacing the difficulty scale with two quantile models worked.** The old band took one central
prediction and stretched it by a predicted difficulty, which assumes every tender's error has the
same shape, only wider or narrower. Real awards are not like that: a tender can have a firm floor
and a long tail above it. Fitting one model to the low edge and one to the high edge, then padding
both by a conformal margin, lets the two edges move independently.

It answered 31,891 of the test tenders instead of 29,107, and covered more of them. The median
error rose from 33.9 to 34.8 percent, and that rise is composition, not decay: the central estimate
comes from the same model in both, so the only reason the error moved is that 2,784 tenders it used
to decline are now answered, and those are the hard ones.

### Giving the model the buyer's own past price level

The model already had the buyer as a category, so in principle it could learn what each one pays.
In practice it has to learn that level by level from whatever rows it happens to see, and most
buyers are rare. Handing it the running average of what this buyer has paid before, and what it has
paid before under this same procurement method, is the same evidence in a shape it can use. Only
awards signed earlier count, so no tender is ever informed by its own outcome.

| | Without | With |
|---|---|---|
| Tenders answered by the history route | 31,891 | 32,136 |
| Median error | 37.0 percent | 36.6 percent |
| Inside the band | 79.4 percent | 79.4 percent |
| Typical band | 5.06x | 4.92x |
| Declined | 21.4 percent | 20.8 percent |

Every figure moves the right way at once, which is what separates a real effect from noise: a
coincidence moves some up and some down. It answers more tenders, with narrower bands, at the same
coverage. The drop in declines is about three times its own sampling error. Kept.

### How narrow can the security band get?

The band was 1.42 times wide, which on a one crore tender is a forty lakh spread, so it was worth
asking what sets it. The award is between 30 and 43 times the security at the tenth and ninetieth
percentiles, and that spread is the band.

| Change | Error of the middle estimate | Width needed to cover 80 percent |
|---|---|---|
| One multiple per procurement method | 8.25 percent | 1.432x |
| A multiple per buyer, pulled toward its method | 7.69 percent | 1.409x |
| A model of the multiple on buyer, method, category, size and date | 8.14 percent | 1.433x |

**The buyer's own habit helps; a model of it does not.** Buyers set the security as a share of
their own estimate and keep to their own share, so their past awards say more than their
procurement method does. A gradient boosted model given the same information plus size and date
did no better than the method median, and an earlier in-sample figure suggesting per-buyer medians
could reach 1.25x was overfitting: each buyer's median was measured on the very rows it was scored
against.

**The width is close to a floor, and the reason is structural.** The security pins the buyer's
estimate. What remains is the gap between that estimate and the winning bid, which competition
sets. The portal publishes neither the losing bids nor how many bidders turned up, so that
variation cannot be modelled from public data. It is not a modelling failure, it is missing data.
Splitting by tender size does not help either: every quarter of tenders, from four lakh to nearly
three crore, needs between 1.38 and 1.42 times.

**A calibration bug surfaced on the way.** The band's edges were measured on the same rows the
multiplier was fitted on. With one median per method that barely mattered. With a median per buyer
it flattered badly: the band looked like 1.32x while covering 75.5 percent of later awards and
promising 80. The edges are now measured on securities the multiplier never saw.

**Bands age, so coverage is now reported against how stale the band is.** The share buyers ask for
drifts upward and the spread has widened month by month, from 1.29x in January to 1.43x in
September. A band set in June covers June far better than September.

| Band was this old when the award landed | Awards | Inside the band |
|---|---|---|
| Within a week | 472 | 81.8 percent |
| One to three weeks | 655 | 75.7 percent |
| Three to six weeks | 845 | 77.3 percent |
| Over six weeks | 1,458 | 75.7 percent |

The model retrains every night, so a live tender meets a band that is a day or two old, which is
the first row. The accuracy page publishes the whole table and keeps the conservative
whole-window figure in its headline table, because a number that only holds at the best horizon
should never be quoted alone.

### The tender document price is not a second security

A notice publishes two prices the buyer chose: the refundable security, and the fee to download the
tender document. The security is a fixed share of the buyer's cost estimate, which is why it pins the
award so tightly. The document fee looked like it might be a second such signal, and it is published
more often than the security is.

It is not. Across 2,418 awards that published one, the ratio of award to document fee runs from about
570 at the tenth percentile to 7,230 at the ninetieth, a spread of 12.7 times. The security's ratio
spans 1.5 times over the same range. Pricing an award straight off the document fee gives a median
error of 51 percent, worse than the history route it would have replaced. The fee is set on coarse
value slabs, so it says which bracket a tender is in and almost nothing more. Rejected.

## Category

### First, how much does this model move when nothing changes?

Everything below rests on this number, and it should have been measured first. Running the same
cross-validation three times, on the same data, with the same seed, gives these deferral rates:

| Run | Declines | Macro F1 |
|---|---|---|
| 1 | 44.41 percent | 0.658 |
| 2 | 45.06 percent | 0.649 |
| 3 | 46.11 percent | 0.642 |

A spread of 1.7 points of deferral and 1.6 points of macro F1, from nothing at all. The training is
not bit-reproducible, and the deferral threshold is chosen at a percentile of a confidence
distribution, so a difference in the last decimal place of a probability moves which tenders fall
either side of the line.

Pinning every maths library to a single thread was the obvious suspect, and it is only half the
story: single-threaded, the deferral rate repeats exactly, but macro F1 still moves 1.3 points
between two identical runs. Correctness is stable while the identity of the wrong answer is not, so
predictions on near-ties still shift, and macro F1 reads those shifts. Single-threading would cost
several times the training time and still leave macro F1 unstable, so the fix is to pool runs rather
than chase bit-reproducibility.

That is the floor. Any change to this model worth less than about two points is indistinguishable
from chance on a single run, and several comparisons made earlier in this project were inside it and
should not have been called results. The model now pools three runs for every published figure and
prints the spread beside them.

### Training only on the decisive labels makes it much worse

The portal's tags are noisy, so the obvious move is to train only on labels that won by a clear
margin of keywords and keep scoring on all of them. Discarding the 23 percent of labels decided by a
single keyword against a close second:

| | Every label | Decisive labels only |
|---|---|---|
| Declines at 93 percent accuracy | 44.4 percent | 53.3 percent |
| Macro F1 | 0.648 | 0.577 |
| Accuracy if forced to answer | 76.0 percent | 71.9 percent |

Nine points of deferral and seven of macro F1, far outside the noise floor. The labels that look
weakest still carry more signal than the rows are worth losing. Rejected, and worth remembering: the
first version of this experiment had a guard that silently refused to apply the filter at all, so it
produced three sets of numbers that differed only by the noise above and looked like a mild
improvement. The guard was found only because the arms should have been bit-identical and were not.

### Does the buyer's own history still help? No longer measurably

A hospital does not buy bridges, so who is buying is evidence about what is being bought, and this
model multiplies its text probabilities by the buyer's own category history. That was worth several
points of deferral when the label set was smaller. With 6,640 labels, and each measurement pooling
three cross-validations:

| | Without the buyer's history | With it |
|---|---|---|
| Declines at 93 percent accuracy | 45.1 percent | 44.8 percent |
| Macro F1 | 0.643 | 0.646 |
| Accuracy if forced to answer | 75.8 percent | 75.6 percent |

Three tenths of a point, against a run-to-run spread of eight tenths to nearly two points. The
honest reading is that the feature no longer earns its place on the evidence available, and that an
earlier version of this comparison, which put its value at nine tenths of a point, was reading noise.
It is kept because it costs nothing and was genuinely useful at a smaller label set, not because
this measurement supports it. Worth retesting when the label set doubles.

### What limits this model is the label, not the model

The portal's category tags are the only honest ground truth available, and they are themselves
noisy. A tender carries a median of 27 tags, and where a tender's own description also resolves to a
category, it agrees with the tag-derived label only 50.3 percent of the time across 3,626 tenders.

That is the thing to fix. It does not make the reported accuracy wrong, since it is measured against
those tags either way, but it does mean a large share of the apparent mistakes are cases where the
tags and the tender's own words disagree, and no amount of modelling resolves that from the inside.

## What the larger archive did to the headline

Retraining on 682,612 awards rather than 210,544 moved the security route's coverage from 83.9
percent to 79.7 percent, and left its median error and band width where they were, at 8.7 percent and
1.42 times. The coverage did not fall because the model got worse. It fell because the route is now
scored under a stricter rule.

Every published security in the archive is recent, since detail pages have only been fetched for
about the last year. Split the whole archive by date and all of them land after the cut, so the
multiplier has nothing to learn from and the route switches itself off entirely, which is what the
first full-archive run did: zero securities scored. The route now gets its own forward split, fitted
on 1,673 earlier securities and scored on the 423 signed later. Coverage of 79.7 percent against a
target of 80 is a band doing exactly what it promises. The earlier 83.9 percent was a band quietly
wider than it needed to be.

### Where the 39 percent actually comes from

The category model declined 38.5 percent of tenders at 93 percent accuracy, and the target was 15.
Three ways of improving the model itself were tested, then two ways of changing what is measured,
all pooled over three cross-validations on the same day's data.

| Variant | Tenders scored | Classes | Declines at 93% | Declines at 95% | Accuracy if forced | Macro F1 |
|---|---|---|---|---|---|---|
| The published model | 17,869 | 15 | 38.5% | 47.9% | 77.8% | 0.655 |
| Plus the declared Goods/Works/Services and method | 17,869 | 15 | 38.5% | 47.6% | 78.1% | 0.657 |
| CPV fine labels, with nature and method | 11,363 | 15 | 37.4% | 44.9% | 79.0% | 0.719 |
| Multilingual sentence embeddings, CPV sectors | 16,644 | 13 | 23.9% | 31.0% | 83.1% | 0.599 |
| Embeddings and word counts blended 50/50 | 16,644 | 13 | 19.5% | 26.0% | 84.8% | 0.662 |
| Word counts, CPV sector labels, with nature | 16,644 | 13 | 18.3% | 24.6% | 85.1% | 0.683 |
| Old labels, only tenders the CPV labeller can label | 14,595 | 15 | 22.8% | 30.9% | 83.6% | 0.664 |
| Old labels merged to sectors, same tenders, with nature | 14,429 | 13 | 16.6% | 23.1% | 85.7% | 0.701 |

**Nothing that changes the model moved the 15-category task.** The declared nature and method added
a tenth of a point. Reading labels from the official CPV hierarchy gave 37.4 percent on a smaller
population. Sentence embeddings were worse than word counts on their own and dragged a blend down
with them, so they were not adopted, which also keeps PyTorch and a nightly encoding step out of the
pipeline.

**Everything that moved the number changed what is being measured.** Scoring only the tenders
whose codes carry category information takes the same old labels from 38.5 to 22.8 percent. Merging
roads, buildings and water into one construction class takes it to 16.6. The last row is the control
that matters: the old keyword labels, merged and scored on exactly those tenders, do slightly better
than the CPV labels. The CPV labels agree more often with what buyers declare about their own
notices, 5.8 against 7.3 percent contradictions, but they do not make the model more confident.

So a published figure in the high teens would be a redefinition, not a better model. There is a
real case for the redefinition, because the portal's own ground truth does not record roads versus
buildings versus water for 77 percent of construction tenders, and records no usable category at
all for about one tagged tender in five. But it has to be published as what it is, beside the
full-population figure, never in its place.

This also corrects the section above. The label was not what limited the model in the way that
section claimed: fixing the labeller's substring errors made the labels more truthful without making
the tenders easier to classify.

**Adopted: sectors, scored where the codes support them.** Bidefy now reads categories as thirteen
sectors from the CPV codes, and shows construction's type only where the buyer stated it. The CPV
labels were chosen over the merged keyword labels despite scoring 1.7 points worse on the same task:
every CPV label traces to an official code, while the keyword labels carry errors anyone can find in
minutes, such as site preparation filed under food. The accuracy page states which tenders the
figure covers, and the fifteen-category figure stays here beside it.

## What an archived detail page is actually worth

The security route is so much better than the history route that the obvious move is to fetch detail
pages for tenders that have already been awarded, not just for open ones, so the model has more of
them to learn from. Only 5,794 of the 125,136 awards signed since September 2025 had been fetched.

The first 603 pages of that crawl say what the rest will cost. The portal no longer serves every
archived page in full:

| Out of 100 archived award pages fetched | |
|---|---|
| Come back as a stub, with nothing on them | 41 |
| Come back complete | 59 |
| Carry category tags | 59 |
| Publish a security | 38 |

So roughly five requests buy three usable pages. An earlier estimate put the security rate at 85
percent, taken from open tenders, and open tenders are not a fair guide: they are current, and the
portal serves them whole. Against archived awards the rate is 38 per hundred fetched.

The lever is still much the largest available. Fetching the remaining 119,342 awards in the window
would add roughly 45,000 securities against the 2,096 on record, and roughly 70,000 category labels
against 6,640. It is a twentyfold increase in the evidence behind the precise route and a tenfold
increase in the category training set, and it needs no modelling at all. At one request a second it
is about 33 hours of crawling, which is why it now has an hour of every nightly run.

## The two rejected ideas worth remembering

**Keyword labels.** Adding twenty thousand labels from a keyword rule raised the published accuracy
and destroyed the real one, from 89.8 percent to 55.4 percent against the portal's own tags, because
the model was partly being scored on the rule it had been taught to copy.

**Richer text features and finer security multipliers.** Both were tried, neither moved a number
outside its noise, and both were reverted rather than kept for the sake of having changed something.
