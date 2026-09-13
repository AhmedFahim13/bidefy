# Bidefy

Tender intelligence for Bangladesh's public e-GP procurement portal.

- Design spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`
- Command centre: published by the Pages workflow (link added once live)

## Crawler

```bash
uv sync
uv run pytest
uv run python -m bidefy.crawler.run --endpoint tenders --mode backfill --budget-min 60
uv run python -m bidefy.crawler.run --endpoint tenders --mode delta
```

Runs nightly on GitHub Actions at one request per second, checkpointed in `checkpoints/`,
data committed under `data/raw/`. Backfill resumes across nights until `next_page` passes
`total_pages`; scheduled runs then switch to delta automatically.
