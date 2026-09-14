export type Term = { key: string; term: string; short: string; long?: string };

export const GLOSSARY: Term[] = [
  { key: "egp", term: "e-GP", short: "Bangladesh's national electronic government procurement portal, eprocure.gov.bd, where public bodies publish tenders and awards.", long: "Run by the Bangladesh Public Procurement Authority (BPPA). Almost every ministry, agency and state company buys through it. Bidefy reads only its public, login-free pages." },
  { key: "bppa", term: "BPPA", short: "Bangladesh Public Procurement Authority, the regulator that owns e-GP and the procurement rules." },
  { key: "tender", term: "Tender", short: "A public invitation to bid for a contract: the buyer describes what it needs, sets a closing date, and firms submit priced offers.", long: "On e-GP the invitation is called an IFT (Invitation for Tender). A tender is 'Live' between publication and closing." },
  { key: "procuring-entity", term: "Procuring entity", short: "The office that is actually buying and will sign the contract, for example a district road division or a hospital.", long: "Entities sit under an organisation, a division and a ministry. Bidefy profiles entities because award patterns live at this level, not the ministry level." },
  { key: "ministry", term: "Ministry, division, organisation", short: "The three administrative layers above a procuring entity. Ministry is the top; organisation is the agency the entity belongs to." },
  { key: "reference", term: "Reference number", short: "The buyer's own file number for the tender. Bidefy uses e-GP's numeric tender id instead; the reference is shown for matching paperwork." },
  { key: "nature", term: "Nature: Goods, Works, Services", short: "What is being bought. Goods are supplies, Works are construction, Services are consultancy or non-consulting services." },
  { key: "otm", term: "OTM", short: "Open Tendering Method: anyone eligible may bid. The default for most public purchases." },
  { key: "ltm", term: "LTM", short: "Limited Tendering Method: only a shortlist of enlisted firms is invited, used for smaller or specialised purchases." },
  { key: "rfq", term: "RFQ", short: "Request for Quotation: a quick quote-based method for low-value purchases with a short deadline." },
  { key: "dpm", term: "DPM", short: "Direct Procurement Method: buying from one supplier without competition, allowed only in defined cases such as emergencies." },
  { key: "ostetm", term: "OSTETM", short: "One-Stage Two-Envelope Tendering: technical and financial offers are submitted together but opened separately." },
  { key: "tstm", term: "TSTM", short: "Two-Stage Tendering: a technical round first, then priced bids from those who pass." },
  { key: "nct", term: "NCT", short: "National Competitive Tendering: open to firms in Bangladesh." },
  { key: "ict", term: "ICT", short: "International Competitive Tendering: open to foreign firms too, usually for larger or donor-funded contracts." },
  { key: "security", term: "Tender security", short: "A refundable deposit a bidder lodges with the bid, usually a small percentage of the buyer's cost estimate.", long: "The estimate itself is not published. Because security is set as a share of it, Bidefy uses the security amount as a proxy for the size of the tender." },
  { key: "document-price", term: "Document price", short: "The fee to download the full tender document. A signal of size, not of value." },
  { key: "publishing-closing", term: "Publishing and closing", short: "The window in which bids are accepted. Bidefy shows days left and turns the badge amber inside three days." },
  { key: "corrigendum", term: "Corrigendum", short: "An official correction or amendment to a published tender, for example a new closing date." },
  { key: "re-tender", term: "Re-tender", short: "The buyer cancelled the first round, often for too few valid bids, and issued the tender again." },
  { key: "status", term: "Status", short: "Live means open for bids. Being processed means closed and under evaluation. Contract Awarded means a winner has signed. Cancelled and Rejected end the process." },
  { key: "award", term: "Award (NOA)", short: "Notification of Award: the buyer names the winning bidder and the contract value. Bidefy indexes these as awards." },
  { key: "value", term: "Crore and lakh", short: "Bangladeshi counting units. 1 lakh is 100,000 taka; 1 crore is 100 lakh, or 10 million taka. Award values on e-GP are stated in crore." },
  { key: "category", term: "Category", short: "Bidefy's own grouping of tenders into fifteen kinds, predicted from the title. It shows a category only when confident and says so when it declines." },
  { key: "band", term: "Predicted award band", short: "Bidefy's estimate of the likely award value, shown as a range that holds about four times in five, with the most likely value inside it." },
  { key: "bidder", term: "Bidder", short: "A firm that wins awards. Bidefy merges spelling variants of a firm's name into one profile and lists the variants it merged." },
];

export const BY_KEY: Record<string, Term> = Object.fromEntries(GLOSSARY.map((t) => [t.key, t]));

const ABBREVIATIONS: Record<string, string> = { OTM: "otm", LTM: "ltm", RFQ: "rfq", RFQU: "rfq", DPM: "dpm", OSTETM: "ostetm", TSTM: "tstm", NCT: "nct", ICT: "ict" };

/** One-sentence definition for an abbreviation as shown on e-GP, or an empty string. */
export function define(abbr: string | null | undefined): string {
  if (!abbr) return "";
  const key = ABBREVIATIONS[abbr.trim().toUpperCase()];
  return key ? BY_KEY[key].short : "";
}
