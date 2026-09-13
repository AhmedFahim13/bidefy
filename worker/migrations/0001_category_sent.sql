ALTER TABLE tenders ADD COLUMN category TEXT;
ALTER TABLE tenders ADD COLUMN category_confidence REAL;
CREATE INDEX IF NOT EXISTS idx_tenders_category ON tenders(category);
CREATE TABLE IF NOT EXISTS sent (
  subscription_id TEXT NOT NULL, tender_id TEXT NOT NULL, sent_at TEXT NOT NULL,
  PRIMARY KEY (subscription_id, tender_id)
);
