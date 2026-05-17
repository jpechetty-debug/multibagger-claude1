# MultiBagger Implementation Roadmap v3.0 - Required Patch Notes

> Companion patch notes for the DOCX roadmap. The DOCX source is not present in this checkout, so apply these changes to the roadmap source document before publishing v3.1.

---

## Critical Fixes

### WebSocket Live Feed Must Be Multi-Worker Safe

Do not store global live-feed truth in module-level lists or dictionaries such as:

```python
connected_clients: list[WebSocket] = []
live_prices: dict[str, dict] = {}
```

Uvicorn workers are separate OS processes, so each worker has separate memory. In a 4-worker deployment, a tick handled in one worker only reaches clients connected to that same worker.

Required roadmap change:

- Keep each worker's local WebSocket client set only for local fan-out.
- Publish Shoonya ticks to a cross-worker bus.
- Subscribe each worker to that bus and fan out messages to local clients.
- Budget the Redis command volume before selecting Upstash Pub/Sub for live ticks.

Recommended implementation note:

```python
# services/live_broadcaster.py
import json
from upstash_redis.asyncio import Redis

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
CHANNEL = "live:prices"

async def publish_tick(sym: str, data: dict) -> None:
    await redis.publish(CHANNEL, json.dumps({sym: data}))
```

### Shoonya `on_tick` Must Be Thread-Safe

Shoonya callbacks may run outside the asyncio event loop. Do not call `asyncio.create_task()` directly from `on_tick`.

Required roadmap change:

```python
import asyncio

_loop: asyncio.AbstractEventLoop | None = None

def on_tick(tick: dict) -> None:
    sym = tick.get("tk")
    data = {"price": tick.get("lp"), "chg": tick.get("pc")}
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(publish_tick(sym, data), _loop)
```

Set `_loop` during FastAPI lifespan startup.

### WebSocket Disconnect Handling Must Be Idempotent

Replace unsafe removal:

```python
connected_clients.remove(ws)
```

with:

```python
finally:
    if ws in connected_clients:
        connected_clients.remove(ws)
```

### Celery Requires Upstash Native Redis TCP URL

Clarify environment variables:

| Variable | Protocol | Use |
| -------- | -------- | --- |
| `UPSTASH_REDIS_REST_URL` | HTTPS REST | Upstash REST SDK, REST rate limiting |
| `UPSTASH_REDIS_REST_TOKEN` | token | Upstash REST SDK auth |
| `UPSTASH_REDIS_TCP_URL` | `rediss://` | Celery broker/backend, redis-py |

Roadmap code should use:

```python
CELERY_BROKER = os.environ["UPSTASH_REDIS_TCP_URL"]
CELERY_BACKEND = os.environ["UPSTASH_REDIS_TCP_URL"]
```

Add this note: In the Upstash dashboard, copy the `rediss://` URL for Celery, not the REST URL.

---

## High-Priority Design Changes

### Store NSE Tokens In The Database

Remove hardcoded `NSE_TOKENS` dictionaries from the roadmap.

Required schema direction:

```sql
ALTER TABLE stocks ADD COLUMN nse_token TEXT;
ALTER TABLE stocks ADD COLUMN token_last_refreshed_at TIMESTAMPTZ;
```

Required behavior:

- Load subscriptions from the `stocks` table.
- Refresh tokens on a weekly cadence or after symbol/corporate-action changes.
- Fail loudly when a watchlist symbol lacks a token.

### Canonicalize Screener Cache Keys

Replace interpolated float cache keys with a hash of a canonical filter dictionary:

```python
import hashlib
import json

def screener_cache_key(filters: dict) -> str:
    canonical = json.dumps(
        {k: round(float(v), 4) if isinstance(v, (int, float)) else v for k, v in sorted(filters.items())},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "screener:" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

### Authenticate `/ws/prices`

The roadmap must not publish an unauthenticated persistent WebSocket endpoint.

Required behavior:

- Validate a short-lived JWT or equivalent access token during connect.
- Close unauthorized clients with code `1008`.
- Add connection limits/rate limits at the app or edge layer.

### Add Frontend Reconnection Logic

The React live-price hook must expose connection state and retry with exponential backoff.

Roadmap requirements:

- `connected` state exposed to UI.
- Exponential backoff from 1s up to 30s.
- Cleanup timers and close sockets on unmount.
- Ticker UI displays a reconnecting state during outages.

---

## Medium-Priority Additions

### Add Phase 0: Current State Audit

Before migration:

1. Count and list all `yfinance` call sites.
2. Export the current SQLite schema.
3. Document user-facing vs. internal endpoints.
4. Add `USE_SHOONYA=false` as a rollback feature flag.
5. Tag the current commit as `v1-pre-migration`.

### Subscribe To Dynamic Watchlist Tokens

Replace fixed subscriptions such as:

```python
api.subscribe(["NSE|22597", "NSE|16669", "NSE|538"])
```

with:

```python
tokens = fetch_all_nse_tokens()
api.subscribe([f"NSE|{token}" for token in tokens])
```

### Revisit Upstash Free-Tier Economics

Redis Pub/Sub for 50 symbols ticking every second during market hours can exceed free-tier command volume by a wide margin.

Roadmap options:

- Keep live prices in-process for single-worker MVP deployments only.
- Use a paid Redis plan and update the monthly budget.
- Reduce tick fan-out volume through batching/throttling.

### Document Neon Pool Math

For Neon free tier with 10 max connections and 4 Uvicorn workers:

```python
engine = create_engine(DATABASE_URL, pool_size=2, max_overflow=1)
```

Or use Neon PgBouncer transaction pooling and document the connection model explicitly.

---

## Low-Priority Additions

### Add Shoonya Session Health Check

```python
@router.get("/api/health/shoonya")
async def shoonya_health():
    try:
        api = ShoonyaSession.get()
        result = api.get_quotes(exchange="NSE", token="22597")
        return {"status": "ok", "sample_price": result.get("lp")}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
```

### Add Zustand Persistence Warning

If watchlist and theme live in `localStorage`, the roadmap should state that browser storage clearing or device switching loses preferences. Future Phase 4+ can sync preferences to a `user_preferences` table.

---

## Cross-Cutting Roadmap Rule

Every data-layer phase should reference `/data-integrity` from `.agent/workflows/data-integrity.md` as the sanity check after changes to Shoonya, market data, screener logic, cache, database schema, or live prices.
