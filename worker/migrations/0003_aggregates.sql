ALTER TABLE bidders ADD COLUMN recent_awards TEXT;
ALTER TABLE procuring_entities ADD COLUMN recent_awards TEXT;
ALTER TABLE procuring_entities ADD COLUMN top_bidders TEXT;
DROP INDEX IF EXISTS idx_tenders_closing;
