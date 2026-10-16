# Data and architecture improvement plan

Date: 16 October 2026  
Status: proposed implementation plan; implementation has not started under this request.

## Objective

Make the dashboard's data, scores, production persistence, and validation results trustworthy. Use the downloaded data already available in this repository and the Finding Multibagger NSE sibling project. Preserve source evidence and existing values until replacements meet explicit acceptance rules.

This plan evaluates the pasted architectural report against current source. It does not treat its reported specialist-agent reviews or green checks as independent evidence of correctness. No application changes, deployments, dependency installations, or database migrations are part of this planning turn.

## Assessment of the pasted report

| Report statement | Current evidence | Planning consequence |
|---|---|---|
| Every validation gate passed | Raw logs, exact scope, test counts, revision and environment are absent from the paste. Existing April logs show four passes and two failures, but are too old to establish current status. | Establish a new reproducible baseline; neither the old failures nor the pasted passes establish today's readiness. |
| Database schema and migrations validated | The checklist's schema validator discovers Prisma/Drizzle files, has no SQLAlchemy/Alembic validation, and returns success when it finds no schemas. | Replace this gate with real application migration and schema checks. |
| Core unit and integration tests passed | The wrapper can exit successfully with no detected test framework. Its detection does not independently run both the Python application and nested React frontend. | Require explicit suite paths and nonzero collection counts; distinguish offline, integration, live, skipped and unavailable checks. |
| Full verification was executed | Current `verify_all.py` requires `--url`. The pasted invocation omits it. Both orchestrators can return a green aggregate with skipped checks. | Capture actual commands and exit codes. Missing required checks cannot satisfy release readiness. |
| Database layer is async and ready for production | `db/engine.py` uses synchronous `create_engine` and `sessionmaker`. Repository helpers still use SQLite metadata queries, placeholders and runtime schema changes. | Keep blocking work off the event loop; fix SQL dialect and transaction behavior rather than only changing connection factories. |
| Move every direct SQLite call to PostgreSQL | Production SQLite writes are prohibited by the manifesto. Read-only archives, local analysis and reproducible enrichment legitimately use SQLite. | Migrate reachable production paths and retain explicitly local archive adapters. |
| `yfinance` is a remaining architectural dependency | Current runtime worker code still labels and uses yfinance download paths. The reported approximate file count has not been independently reproduced. | Inventory reachable use by capability, then replace it without losing price, benchmark, action or fundamental coverage. |
| Shoonya can replace all data feeds | The manifesto requires Shoonya for acquisition, but the pasted report does not establish coverage for annual accounts, quarters, ownership or historical vintages. | Prove capabilities separately and retain user-authorized downloaded financial evidence. Do not substitute quote data for statements. |
| Frontend lacks Query/Zustand | Confirmed in current `web-ui/package.json`. | Migrate shared server data incrementally; retain local component state where appropriate. |
| `worker/background_jobs.py` defines Celery tasks | It contains runtime price-refresh loops. Celery configuration is separately present in `worker/celery_app.py`. | Trace both worker entry points and their writers/schedules. |
| Parquet guarantees scalable history | It provides a useful analytical store, but the inspected local lake contains older fundamental snapshots. Capacity and price-history completeness need measurements. | Preserve typed, dated datasets and benchmark relevant reads; do not assume partitioning alone establishes correctness or scalability. |
| Security and sub-Rs. 500/month hosting are established | No sufficient security test scope, deployment measurements or billing evidence was supplied. | Treat both as release conditions requiring evidence, not existing guarantees. |

The toolkit's `.agent/ARCHITECTURE.md` describes agent tooling. `Newmultibagger-main/ARCHITECTURE.md` describes the application. Keep these scopes separate when making application decisions.

## Existing data work to reuse

The completed review artifacts from earlier in this chat are a starting snapshot, not a live inventory. Recheck their source versions before implementation:

- 915 original picks retained without overwriting prices or scores.
- Local downloaded prices for all 915, with two stale observations; 42 future fundamental dates and 50 missing/unverified listing dates were identified in that snapshot.
- Finding Multibagger NSE has matched fundamentals and annual histories for 364 picks and quarterly histories for 359.
- 907 picks have an exact cross-project ISIN match.
- 168 currently missing-field candidates across 68 picks meet the import's evidence-review checks: CFO/PAT 38, debt/equity 8, five-year PAT CAGR 39, ROA 42, ROCE 40 and ROE 1.
- Imported reference history includes 2,222 annual rows, 4,515 quarterly rows and two separate price sources covering 2017 through October 2026. Source histories overlap and have different adjustment bases.
- Newer dated prices are available for 109 picks compared with the first local review.

These candidates are not approved replacements. Original source bodies and archive response hashes were not independently revalidated during import. ISIN agreement does not establish reporting-scope or fiscal-period equivalence, and issuer metadata does not supply missing listing dates.

Working artifacts: `DATA_QUALITY_REVIEW.md`, `Newmultibagger-main/ops/enrich_from_local_data.py`, `Newmultibagger-main/ops/import_external_data.py`, and `Newmultibagger-main/reports/local_enrichment/2026-10-16-cross-project-final.db`.

## Implementation sequence

### Phase 0 — Establish truthful verification and source policy

Priority: P0. Start here.

1. Record the revision, dirty working-tree diff, dependency versions and input dataset manifests. Preserve unrelated ongoing edits, including current lint, SEO and DQ changes.
2. Capture full stdout/stderr, command, working directory, exit code, duration, suite identity, test counts and skipped counts in a machine-readable verification artifact.
3. Use explicit outcomes: PASS, FAIL, SKIPPED, NOT_APPLICABLE and UNAVAILABLE. A missing required checker, unsupported schema, zero required tests or missing required environment cannot produce release PASS. Optional checks may remain explicitly not applicable with reasons.
4. Run the Python backend and React frontend checks from their actual project directories. Use the selected interpreter consistently instead of a bare `python` that can resolve elsewhere. Pin compatible lint tools and document configuration ownership; do not weaken rules to manufacture a green result.
5. Replace the Prisma/Drizzle-only gate for this application with SQLAlchemy/Alembic schema and migration checks. Keep the generic checker only for projects it actually supports.
6. Record a source policy by data class: new live acquisition follows the Shoonya requirement; retain the user's authorized downloaded NSE/BSE statement evidence, bhavcopy and FYERS archives as dated analytical inputs. Reconcile the manifesto wording explicitly rather than silently deleting useful archives or introducing new scraping.

Deliverables: verification JSON/logs, backend/frontend command matrix, required-gate policy, and source-capability policy.

Acceptance: a deliberate failing check fails the aggregate; a missing required checker and zero collected required tests cannot pass; schema results name the actual SQLAlchemy/Alembic objects checked; the full verification command includes a real test URL when E2E/performance are required.

### Phase 1 — Repair data correctness before promotion

Priority: P0. Depends on Phase 0's baseline and source definitions.

1. Separate `period_end`, observed `published_at`, estimated availability, `fetched_at`, price session/date and `scored_at`. Evaluate availability against the scoring cutoff in IST.
2. Quarantine future and unverified publication dates. Do not replace them with today's date. Keep the last verified eligible observation where available.
3. Preserve `validate_record` findings in scoring output and write null replacements back. An invalid input must not survive merely because its sanitized value is null.
4. Preserve raw values and correction history. Revalidation must not erase clamping/scaling evidence or increase apparent quality for the same observation.
5. Calculate completeness from a fixed, versioned required-field contract. Distinguish missing values, real zero, uncomputed results and not-applicable metrics.
6. Measure freshness per active symbol and per data class. Include missing symbols in the denominator. Database failures must return unavailable/unknown status, not an apparently healthy empty universe.

Deliverables: date/availability contract, corrected validation propagation, deterministic quality computation, and per-symbol freshness results.

Acceptance: future observations cannot generate eligible scores; original invalid values cannot reach factor calculations; repeated validation preserves findings; fresh + stale + expired + missing equals the active universe; storage failures cannot appear healthy. Use focused offline regressions for each behavior.

### Phase 2 — Promote downloaded evidence through a controlled backfill

Priority: P1. Depends on Phase 1.

1. Refresh input manifests and reopen sibling databases read-only. Reject or obtain a consistent snapshot for a nonempty WAL or source that changes during extraction. Do not checkpoint or modify another project's database as part of importing it.
2. Validate issuer identity, exact fiscal period, consolidated/standalone scope, currency, unit scale, formula and publication/observation availability for every proposed replacement. Check original document bodies/hashes for adopted fields, not just top-level metadata.
3. Preserve the explicit fraction-to-percent conversion for CAGR. Distinguish closing-equity ROE from average-equity ROE and closing-assets ROA from average-assets ROA. Do not map quarterly EPS growth to long-term growth by name similarity.
4. Assign ACCEPTED, REJECTED or DEFERRED with reasons to every candidate. If the target's period, scope or formula is unknown, defer it rather than guessing.
5. Pilot a small stratified set from the 68 affected picks, covering every target field, both missing and conflicting values, a unit conversion, and incomplete evidence. Produce before/after values, source references and score deltas.
6. Apply accepted changes through the application repository in an idempotent import identified by `run_id`, stable source key and before/after audit records. Publish current rows and corresponding history coherently. Recompute affected scores from one declared input version.
7. For price history, validate the needed archive response hashes and corporate-action treatment before using returns. Keep source bases separate until an explicit reconciliation policy establishes comparability. Replace current prices only with eligible, more recent observations; recompute dependent fields together.
8. Add explicit backtest status and observation counts. Repair legacy zero-filled results using execution evidence; retain genuine zero returns and expire waivers only after verification.

Deliverables: candidate decision ledger, pilot reconciliation report, idempotent backfill command, input-versioned scores and rollback records.

Acceptance: every accepted field traces to compatible evidence; every rejected/deferred field remains visible; rerunning produces no duplicate history; score deltas are explainable; rollback restores prior values and versions. The process may accept fewer than 168 candidates and must report the actual count.

### Phase 3 — Make production persistence genuinely PostgreSQL-compatible

Priority: P1. Production cutover depends on validated data/import behavior.

1. Inventory reachable API, runtime-worker, Celery and scheduled-job readers/writers. Classify direct SQLite use as production, local development, archive-only, test or obsolete.
2. Retain SQLite for read-only sibling/archive adapters and local reproducible analysis. Migrate active production access through the canonical repository.
3. Replace raw qmark placeholders, SQLite PRAGMAs/catalog queries, dialect-specific upserts and runtime ALTERs with backend-appropriate SQLAlchemy/Alembic operations. Moving a SQLite query to a PostgreSQL connection is insufficient.
4. Define transaction ownership, rollback, session lifetime and idempotent writes. `get_session()` currently yields a session; do not assume it commits a transaction or is already an async context manager.
5. Keep synchronous SQLAlchemy initially if it is correctly offloaded from async request paths. An async-engine conversion is a separate measured decision, not a prerequisite for fixing data correctness.
6. Reject a missing/SQLite production URL at startup. Confirm TLS requirements and bound the total connection budget across all web and worker processes.
7. Test Alembic upgrades and repository contracts against a disposable PostgreSQL instance. Use local SQLite tests for supported development paths, not as a substitute for PostgreSQL integration tests. Do not assume a TimescaleDB extension is available or required.
8. Rehearse migration with row counts, key uniqueness, value checks, PIT boundaries and a shared data version. Schedule a controlled write freeze/catch-up for cutover and define rollback before switching writers.

Deliverables: writer inventory, backend-neutral repository behavior, tested migrations, production startup guard and cutover/rollback runbook.

Acceptance: all reachable production writes use PostgreSQL; multi-worker duplicate/retry/concurrency tests pass; no silent SQLite fallback or incidental local-database writes occur in production; archive read tools still work.

### Phase 4 — Complete provider and worker boundaries

Priority: P1. Can prepare capability work after Phase 0; production write integration follows Phase 3.

1. Build a capability matrix for quotes, daily history, benchmarks, corporate actions, dividends, annual accounts, quarters and ownership. Trace actual callers rather than using import counts as the migration metric.
2. Implement or complete the Shoonya adapter for the capabilities it supports. Preserve dates, units, issuer identity and adjustment basis. Test token lifecycle, session expiry, timeouts, provider backoff and market holidays with deterministic fixtures.
3. Retain authorized downloaded statement evidence where quote APIs do not provide financial accounts. Missing capability must be visible; do not produce mock production history or fabricate fundamentals.
4. Replace reachable legacy acquisition paths in batches. Compare coverage and values before disabling a fallback. Historical evidence originally obtained from a legacy source remains labeled evidence; retaining it must not trigger new disallowed requests.
5. Keep runtime loops and Celery jobs distinct and ensure each scheduled workload has one owner. Prevent duplicate refreshes across replicas through idempotency and appropriate locking.
6. Validate native Redis TCP/TLS URLs for Celery and standard Redis clients; validate REST credentials only for REST clients. Separate broker and result/cache configuration where their requirements differ.
7. Make provider health reflect the configured providers and measured calls. Separate upstream failure, stale cache, unavailable credentials and cache hits. Enforce IST session-aware refresh behavior.

Deliverables: capability matrix, provider contract tests, migrated callers, worker configuration checks and measured provider telemetry.

Acceptance: production paths make no disallowed acquisition calls; required coverage does not regress; provider outages and token expiry are explicit; no duplicate publications or plaintext credentials appear in logs; Celery rejects a REST URL used as its broker.

### Phase 5 — Align frontend state and show data quality

Priority: P2. Depends on stable API date/quality contracts from Phases 1–2.

1. Add TanStack Query and a shared query client using the repository's dependency/lockfile workflow. Define stable query keys, abort handling, retry rules, freshness and mutation invalidation.
2. Migrate shared stock, score, provider-health and freshness queries incrementally. Consolidate overlapping polling where appropriate.
3. Add Zustand only for genuinely shared client state, such as filters, selected symbols and view preferences. Keep server-persisted watchlists in server state. Retain component-local `useState` where it is sufficient.
4. Display price observation date separately from financial period, publication evidence, stale/missing inputs and current validation findings. Preserve helpful last-known data while clearly identifying its age.
5. Follow the documented design system without mixing a visual redesign into data/state refactoring. Validate accessibility and important loading, empty, unavailable and error states on actual application screens.

Deliverables: shared server-state layer, narrowly scoped client store and visible data-quality states.

Acceptance: duplicate consumers share requests; an older response cannot overwrite newer data; mutations invalidate relevant views; polling does not multiply across mounts; users can distinguish current price age from old financial statements. Frontend lint, build and relevant component tests pass.

### Phase 6 — Verify release behavior, security and operating cost

Priority: release gate. Depends on the work intended for that release.

1. Run the explicit backend, frontend, migration, concurrency and data-quality suites. Run E2E against a known local/staging application using the required URL and record scope and counts.
2. Test authorization on protected API/WebSocket paths and redact API keys, broker credentials, TOTP material, database URLs and tokens. A heuristic scan alone cannot establish absence of vulnerabilities.
3. Exercise provider failure, database failure, worker retries and cache failure. Incomplete data must not receive apparently healthy eligibility or freshness labels.
4. Produce a measured capacity and cost worksheet covering always-on workers, database connections/storage, Redis traffic, hosting, telemetry and any analytical/LLM workload. Demonstrate the manifesto's Rs. 500/month ceiling using the actual deployment configuration and billing/usage evidence; if it cannot be met, propose a smaller topology before deployment.
5. Keep large downloaded databases, generated review outputs and credentials outside source commits and deploy images. Restore-test the backup/rollback path and verify active data/source version after any cutover.

Deliverables: reproducible release evidence, security findings and dispositions, measured resource budget and deployment/rollback runbook.

Acceptance: every required gate has current evidence; no required check is skipped or unavailable; unresolved risks are explicit; the chosen deployment meets the documented resource/cost constraints. This plan does not itself authorize or perform deployment.

## Recommended first implementation slice

Deliver Phase 0's gate corrections and Phase 1's future-date/validation-propagation fixes as small, reviewable changes. Then run Phase 2's stratified backfill pilot using the existing cross-project review. Postpone wholesale database-call replacement, dependency-wide feed removal and frontend state migration until their contracts and coverage are defined.

Implement each slice with a failing regression for its concrete behavior, the change, focused verification, and applicable integration checks. Keep application changes separate from unrelated in-progress lint/SEO edits. A source file count, audit heading, or specialist role label is not an acceptance criterion.

## Evidence references

- Pasted audit: `C:\Users\JYOTHI\.codex\attachments\f78d8a5d-33ec-45c5-8821-5134291ae7f5\Pasted text.txt`.
- Policy: `.agent/rules/PROJECT_MANIFESTO.md:11`; application architecture: `Newmultibagger-main/ARCHITECTURE.md:1`.
- Gate behavior: `.agent/scripts/checklist.py:89`, `.agent/scripts/checklist.py:161`, `.agent/scripts/verify_all.py:150`, `.agent/scripts/verify_all.py:273`.
- Unsupported schema gate: `.agent/skills/database-design/scripts/schema_validator.py:29` and `:108`; no-framework test success: `.agent/skills/testing-patterns/scripts/test_runner.py:157`.
- Database implementation: `Newmultibagger-main/db/engine.py:36`, `:71`; SQLite-specific repository helpers: `Newmultibagger-main/db/repository.py:87`.
- Runtime writers: `Newmultibagger-main/worker/background_jobs.py:276` and `:321`; Celery transport: `Newmultibagger-main/worker/celery_app.py:6`.
- Frontend dependencies: `Newmultibagger-main/web-ui/package.json`.
- Prior data baseline and source limitations: `DATA_QUALITY_REVIEW.md` and `Newmultibagger-main/reports/local_enrichment/2026-10-16-cross-project-final.summary.json`.

Verification for this planning request consists of reading the pasted material, current code through CodeGraph, relevant configuration/docs and existing dated artifacts. The full checklist, production PostgreSQL migration, live provider calls and E2E suite were not rerun during planning. Earlier focused enrichment tests remain evidence only for their specific tested behaviors.
