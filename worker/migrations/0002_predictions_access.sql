CREATE TABLE IF NOT EXISTS predictions (
  tender_id TEXT PRIMARY KEY, q10_lakh REAL, q50_lakh REAL, q90_lakh REAL, deferred INTEGER, model_version TEXT
);
CREATE TABLE IF NOT EXISTS access_requests (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, name TEXT NOT NULL, organisation TEXT NOT NULL, role TEXT,
  bids_on TEXT NOT NULL, value_band TEXT NOT NULL, contact TEXT, note TEXT, ip_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_created ON access_requests(created_at DESC);
