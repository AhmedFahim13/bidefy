-- Every hourly alert run, recorded. With no subscribers the run still examines the tenders
-- published since the last watermark, so this table carries a real number from the first hour
-- while the subscriber count is honestly zero. It is also the only evidence the cron is alive.
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
