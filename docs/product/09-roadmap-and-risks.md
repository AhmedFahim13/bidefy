# What is next, and what could go wrong

## Next, in order of what it would buy

1. **Finish fetching detail pages for awarded tenders.** About 119,000 awards in the reachable
   window still have no detail page. Each complete one adds a category label, and roughly two in
   five add a published security. This is the single largest lever left and needs no modelling at
   all: it widens the precise award route and grows the category training set. It is already an
   hour of every nightly run.
2. **A construction sub-type model.** Construction is one category because buyers rarely state the
   type. Where they do, there are now a few thousand labelled examples, enough to try predicting
   roads against buildings against water from the title alone, published as a separate tier with
   its own accuracy and its own deferral.
3. **Usage numbers.** Nothing currently records how many people subscribe, which filters they pick,
   or which tenders they open. Without that there is no evidence the alerts match what bidders want.
4. **A second country or a second portal.** The crawler, the resolver and the award model are not
   specific to Bangladesh. The security-to-award relationship is, and would have to be re-measured.

## Risks, and what each would cost

**The portal changes its markup.** Everything starts with parsing two list endpoints and one detail
page. A layout change breaks the crawl. Detection is quick, since the crawl aborts after five
consecutive failures rather than writing rubbish, but a fix needs a person. Fixtures captured from
the real pages make the repair a small edit rather than an investigation.

**The portal blocks automated reads.** Nothing in the terms forbids them and the crawl is one
request a second from a single session, but a block would end the product in its current form.
There is no paid API to fall back on.

**A free tier changes.** The whole system sits on GitHub Actions, Cloudflare and Vercel free tiers.
D1's write allowance is the tightest and is already managed to the row. A tightening there would
slow the archive load rather than stop the product; a withdrawal would need a paid plan.

**The ground truth stays noisy.** Categories come from codes buyers pick themselves, and some pick
wrongly: a road maintenance job tagged as computer repair is in the data. That ceiling is now
measured rather than guessed, and it limits how good the category model can ever look.

**One person maintains it.** Every nightly failure so far needed a human to read a log. The guards
added since make silent failure much less likely, but nothing here is on call.

**No demand has been proven.** Existing services sell notice alerts at around 1,050 taka a month.
Bidefy's claim is that the award history, which none of them use, is what bidders actually need.
That is a hypothesis with a working product behind it, not a validated market.
