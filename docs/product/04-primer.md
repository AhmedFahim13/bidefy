# A primer on Bangladesh public procurement

Written for the owner before an interview, and for anyone reading Bidefy who has never bid on a tender. Everything here is what the site assumes you know.

## What a tender is

A tender is how a public body buys without picking a favourite. The buying office, called the procuring entity, publishes what it needs, when bids close, and the rules. Firms submit sealed, priced offers. A committee opens them after closing, checks each bid is complete and eligible, and for most goods and works awards the contract to the lowest responsive price. The buyer then publishes a Notification of Award naming the winner and the value, and signs the contract.

In Bangladesh this runs on one portal, e-GP, owned by the Bangladesh Public Procurement Authority under the Public Procurement Act 2006 and Rules 2008. Around 90 percent of public purchasing by volume goes through it. Every notice, correction and award is public without a login. That is the fact Bidefy is built on.

## How to read a tender notice

| Field on the notice | What it means | What Bidefy does with it |
|---|---|---|
| Tender id | e-GP's number for the notice | The key for everything |
| Reference number | The buyer's own file number | Shown for matching paperwork |
| Procuring entity | The office buying and signing | Profile page with award history and concentration |
| Ministry, division, organisation | The layers above the entity | Filters and the award model |
| Nature | Goods, Works or Services | Shown on cards |
| Method | How bids are invited (see below) | Tooltip, model feature |
| Type | NCT for national, ICT for international bidders | Tooltip |
| Publishing and closing | The bidding window | Days-left badge, alerts |
| Tender security | Refundable deposit, a fixed share of the buyer's secret cost estimate | Proxy for tender size in the award model |
| Document price | Fee for the full document | Shown on the detail page |
| Category tags | The portal's own classification, only on the detail page | Training labels for Bidefy's category classifier |

## The procurement methods

- **OTM, Open Tendering.** Anyone eligible may bid. The default for anything sizeable. Most of what Bidefy indexes.
- **LTM, Limited Tendering.** Only enlisted firms are invited. Smaller or specialised buys.
- **RFQ, Request for Quotation.** Quick quotes for low-value items, short deadlines, thin paperwork.
- **DPM, Direct Procurement.** One supplier, no competition, allowed in defined cases such as emergencies or proprietary parts.
- **OSTETM and TSTM.** Two-envelope and two-stage variants for complex procurements where the technical offer is judged before the price is seen.

## What the statuses mean

Live means bids are being accepted. Being processed means closed and under evaluation. Contract Awarded means a winner has signed. Cancelled and Rejected end the process; Re-Tendered means the buyer will try again, usually because too few valid bids arrived. Corrigendum means a published correction, often a new closing date; Bidefy shows that note separately from the status.

## Money

Values are stated in crore. One crore is ten million taka, one lakh is a hundred thousand, so one crore is a hundred lakh. Bidefy shows amounts under one crore in lakh. The median award in the index is about eleven lakh; one in ten is above 1.2 crore. On the portal some values are keyed in taka by mistake; Bidefy converts anything above 500 crore, because no genuine award in the index is that large.

## What the buyer never tells you

The buyer's cost estimate, the losing bids and the number of bidders are not published. That is why Bidefy predicts a band rather than reporting one, and why the tender security matters: it is the only public number tied to the estimate.

## The five questions a bidder asks

1. Is there a tender I should see today? Alerts by keyword, ministry, category, status.
2. What has this entity paid for this kind of work? The band, and the entity's recent awards.
3. Who usually wins here? The entity's top bidders and the share the leader holds.
4. Is this entity worth my time? Concentration flags: if one firm has won 80 percent of the last twelve months, the odds are stated, not hidden.
5. Who am I up against? Bidder profiles with award history, entities, districts and categories.

## What Bidefy refuses to claim

A pattern is not a verdict. A concentrated entity may simply have one competent local supplier. Bidefy publishes shares and counts and lets the reader decide. The award model publishes its error and its deferral rate together, and declines when the band would be too wide to act on. The category classifier does the same.

## Two sentences for an interview

Bidefy reads the public procurement portal every night, resolves 28,000 bidders from 210,000 awards, predicts what an entity will pay with a calibrated band, and alerts a bidder within the hour. It is free at the alert layer and priced at the intelligence layer, and it declines to answer when it cannot answer honestly.
