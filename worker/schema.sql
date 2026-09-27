CREATE TABLE IF NOT EXISTS tenders (
  tender_id TEXT PRIMARY KEY, reference TEXT, status TEXT, note TEXT, nature TEXT, title TEXT,
  ministry TEXT, organization TEXT, procuring_entity TEXT, pe_id TEXT, procurement_type TEXT,
  method TEXT, published_at TEXT, closing_at TEXT, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tenders_published ON tenders(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_closing ON tenders(closing_at);
CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);
CREATE INDEX IF NOT EXISTS idx_tenders_pe ON tenders(pe_id);

CREATE TABLE IF NOT EXISTS contracts (
  tender_id TEXT PRIMARY KEY, reference TEXT, title TEXT, advertised_at TEXT, ministry TEXT,
  procuring_entity TEXT, pe_id TEXT, method TEXT, district TEXT, signed_on TEXT, awardee TEXT,
  bidder_id TEXT, value_crore REAL, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_contracts_signed ON contracts(signed_on DESC);
CREATE INDEX IF NOT EXISTS idx_contracts_bidder ON contracts(bidder_id);
CREATE INDEX IF NOT EXISTS idx_contracts_pe ON contracts(pe_id);
CREATE INDEX IF NOT EXISTS idx_contracts_district ON contracts(district);

CREATE TABLE IF NOT EXISTS bidders (
  bidder_id TEXT PRIMARY KEY, canonical_name TEXT, variants TEXT, n_awards INTEGER,
  total_value_crore REAL, first_award TEXT, last_award TEXT
);
CREATE TABLE IF NOT EXISTS procuring_entities (
  pe_id TEXT PRIMARY KEY, name TEXT, ministry TEXT, n_contracts INTEGER, n_tenders INTEGER
);
CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, keys_json TEXT NOT NULL, filters_json TEXT NOT NULL,
  created_at TEXT NOT NULL, last_sent_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- These two arrived as migrations (0001 and 0002) and were missing here, so a database built from
-- this file alone could not serve /api/v1/usage: a D1 batch fails as a unit, so one absent table
-- takes the whole endpoint down.
CREATE TABLE IF NOT EXISTS sent (
  subscription_id TEXT NOT NULL, tender_id TEXT NOT NULL, sent_at TEXT NOT NULL,
  PRIMARY KEY (subscription_id, tender_id)
);
CREATE TABLE IF NOT EXISTS access_requests (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, name TEXT NOT NULL, organisation TEXT NOT NULL, role TEXT,
  bids_on TEXT NOT NULL, value_band TEXT NOT NULL, contact TEXT, note TEXT, ip_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_created ON access_requests(created_at DESC);

CREATE TABLE IF NOT EXISTS alert_runs (
  ran_at TEXT PRIMARY KEY,
  candidates INTEGER NOT NULL DEFAULT 0,
  subscriptions INTEGER NOT NULL DEFAULT 0,
  matched INTEGER NOT NULL DEFAULT 0,
  sent INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  pruned INTEGER NOT NULL DEFAULT 0,
  -- 1 when the run threw before finishing. Without this a crashloop writes nothing and reads as a
  -- cron that never fired, which is the distinction this table exists to make.
  errored INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alert_runs_ran ON alert_runs(ran_at DESC);
