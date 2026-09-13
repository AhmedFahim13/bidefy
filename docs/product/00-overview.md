# Overview

Bidefy is tender intelligence for Bangladesh's public procurement portal, e-GP. It indexes every public tender notice and contract award, resolves the messy names of bidders and procuring entities into stable identities, predicts the likely award value of a live tender, flags unusual award patterns with the numbers behind them, and sends web push alerts when a tender matching a subscriber's filters appears.

## The gap it fills

Existing services sell daily notice alerts filtered by category, district and organisation, at roughly 1,050 taka a month. None of them use the 877,000 public contract awards on the same portal. So none can answer the questions a bidder actually has: who wins this kind of tender at this entity, at what value, and how often. Bidefy is that layer. It does not compete on alerts.

## What is deliberately not built

- No WhatsApp or Telegram in version one. Web push only, because it costs nothing and needs no Meta account.
- No payments. The Pro tier shows a request-access form until there is a merchant account.
- No claim of fraud. Flags describe patterns with counts and intervals, never a verdict.
- No mirroring of raw notices. The product publishes derived intelligence.

## Cost

Production cost is zero. GitHub Actions crawls and trains, Cloudflare Workers and D1 serve the site and send push, GitHub Pages hosts this document and the command centre.

## Source facts

| Fact | Value |
|---|---|
| Tender notices indexed | about 625,800 |
| Contract awards indexed | about 877,200 |
| Request rate | one per second, one session, checkpointed |
| Data not published by the portal | losing bids, bidder counts, official cost estimates |

The tender security amount, which each procuring entity sets as a share of its estimate, is the cost proxy for prediction.
