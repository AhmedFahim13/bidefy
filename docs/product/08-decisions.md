# Decisions, and what they cost

Every entry is a choice that could reasonably have gone the other way, with the reason it went this
way and what it gave up.

**Web push, not WhatsApp or SMS.** WhatsApp needs a Meta business account and charges per message;
SMS charges per message. Web push is free and needs no account. It gave up reach: web push does not
work on an iPhone unless the site is added to the home screen, and it is invisible to anyone who
declines the browser prompt.

**Zero production cost, on purpose.** GitHub Actions crawls and trains, Cloudflare Workers and D1
serve, Vercel hosts the site, GitHub Pages hosts this document. The constraint shaped the design
more than any other: it is why the loader counts writes rather than rows, why the crawl resumes
across nights, and why embeddings were rejected on cost as much as on accuracy.

**A band, not a number.** The award model answers with a range and publishes what share of real
awards landed inside it. A single number would be easier to show and would hide how uncertain it
is. The range is what a bidder can actually price against.

**Models may decline.** A classifier forced to answer every time is wrong more often than one
allowed to abstain. Accuracy is therefore never published without the deferral rate beside it.

**The tender security became the core of the award model.** Buyers set a refundable security as a
fixed share of a cost estimate they never publish. That makes it the most valuable number on the
portal, and fetching detail pages to get it cut the band from roughly eleven times wide to one and
a half. Most of the accuracy came from collecting better evidence, not from a better model.

**Categories are read, not predicted, wherever possible.** The portal publishes CPV procurement
codes on each detail page. For a live tender the category is a lookup, not a prediction. The model
covers only the archive.

**Thirteen sectors, not fifteen categories.** Buyers tick a whole construction division for 77
percent of construction tenders, recording nothing about roads versus buildings versus water. The
old taxonomy asked for a distinction the ground truth does not contain, and filled it with keyword
noise, so the site sorted tenders into types their buyers never stated. Construction is now one
category and the type is shown only where a buyer stated it. This gave up granularity that users
might want, and it makes the published deferral figure incomparable to the old one, which is why
both are published.

**The official CPV list over a keyword mapper.** The keyword labels scored slightly better on the
same task, 16.6 against 18.3 percent deferral. The CPV labels were chosen anyway because every one
traces to a published standard, while the keyword labels carried errors anyone could find in
minutes, such as site preparation filed under food.

**Flags describe, never accuse.** Concentration and outlier flags carry counts and intervals, not
verdicts. Public procurement data supports "this buyer awarded 74 of its last 100 contracts to one
firm". It does not support calling that corruption.

**Losing bids are absent because the portal does not publish them.** No amount of crawling
produces a bidder count per tender, so the product never implies one.

**The review queue is decided by rule where a rule is honest.** Thirty thousand borderline name
pairs will never be read by a person. Punctuation, honorifics and legal suffixes are decided
automatically; pairs where one name simply carries an extra word are left for a human, because that
is a judgement and not a rule.
