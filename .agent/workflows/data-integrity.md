---
description: Data layer sanity check for MultiBagger market data, screener, cache, and live feed changes.
---

# /data-integrity - Data Layer Sanity Check

Use this workflow after any change to Shoonya integration, NSE/BSE token handling, stock ingestion, screener queries, cache behavior, or live price streaming.

## Steps

1. Verify Shoonya session health: `GET /api/health/shoonya`.
2. Check `stocks` row count against the expected 50-symbol watchlist.
3. Confirm all watchlist rows have a non-empty `nse_token`.
4. Run `EXPLAIN ANALYZE` on the primary screener query and confirm it uses the expected index path.
5. Verify the latest `last_updated` value in `stocks` is within 24 hours on trading days.
6. Test `/ws/prices` with an authenticated client and confirm at least 3 subscribed symbols tick.
7. Check Redis cache behavior:
   - screener cache hit/miss logs are present,
   - key format is canonicalized,
   - Upstash command volume remains within the current budget.
8. Confirm all market timestamps are IST-aware.

## Pass Criteria

- Shoonya health returns `status: ok`.
- Watchlist count and token coverage match expectations.
- Screener query avoids full-table scans unless the table is intentionally tiny.
- No stale data is served without an explicit stale-data marker.
- Live prices recover after disconnect/reconnect.
- Redis protocol usage is correct: REST URL for REST clients, `rediss://` TCP URL for Celery or standard Redis clients.

## Failure Handling

- Stop deployment if token coverage, Shoonya auth, or stale-data checks fail.
- Log provider payload samples for data-shape regressions.
- Document any known stale-data exception in the release notes.
