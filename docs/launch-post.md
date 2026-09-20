# Launch post

Draft for Fahim to post. Publishing needs his own account, so it is written here rather than sent.
Numbers are the live ones on 2026-09-20; check them against the accuracy page before posting.

---

**I built Bidefy, a tender intelligence layer on Bangladesh's e-GP portal. It runs at zero cost.**

Every public tender notice and every contract award in Bangladesh is published on one portal. The
notices are watched closely. The 877,000 awards behind them are not. That is the gap.

Bidefy reads both every night and answers the question a bidder actually has: what is this tender
likely to be worth, who usually wins this kind of work at this buyer, and at what price.

What it does:

- **Predicts the award value of a live tender.** For roughly 85 percent of open tenders it lands
  within 8.4 percent of the final award, inside a band 1.4 times wide. That comes from a field
  almost nobody models: the refundable security a buyer sets as a fixed share of its own unpublished
  cost estimate.
- **Reads what each tender is for** from the portal's CPV procurement codes, and says so only when
  the codes actually support it. 93 percent accurate on the tenders it answers, declining 16 percent.
- **Flags unusual award patterns** with the counts and intervals behind them, never a verdict.
- **Sends a web push** when a tender matching your filters appears.

What it does not do: no payments, no WhatsApp, no fraud accusations, no mirror of the raw notices.

The part I would put in front of an engineer: every published figure is measured on data the model
never saw, the deferral rate is printed next to every accuracy, and the experiments that failed are
written up beside the ones that worked. The models decline when the evidence is thin, because a
confident wrong answer costs a bidder more than a blank one.

Live at https://bidefy.vercel.app. How it works, what it gets right, and what it still gets wrong:
https://ahmedfahim13.github.io/bidefy/doc.html

Built in eight weeks, on free tiers: GitHub Actions crawls and trains, Cloudflare Workers and D1
serve, Vercel hosts the site.
