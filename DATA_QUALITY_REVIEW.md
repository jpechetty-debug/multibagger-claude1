# Data quality review — 16 October 2026

## Scope and evidence

Used the existing Graphify graph (10,947 nodes, 19,531 links), its vocabulary expansion and BFS queries to locate data acquisition, validation, scoring, and freshness components. The graph was last modified on 6 October 2026 and warns that its old node IDs can collide between same-named files. Graph edges connecting scoring to `validate_record` and `enforce_pit_gate` are tagged INFERRED; both calls were subsequently confirmed in current source through CodeGraph. Current-source findings and database measurements below supplement the graph; they are not presented as facts extracted from the old graph.

Read the working tree as it stands, including the user's existing changes to `modules/data_layer/dq_audit.py`. Ran that audit and aggregate SQL against `Newmultibagger-main/runtime/stocks.db` in SQLite read-only mode. Date comparisons use 2026-10-16. No application code or database rows were changed. These observations describe the local database, not a deployed environment.

Expanded Graphify query: `quality validation audit provenance freshness reconcile schema missing outlier cache fundamentals prices`. Followed with a narrower DQ query and inspection of relevant graph nodes and edges. No graph rebuild was performed.

## Observed data

| Measurement | Result |
|---|---:|
| Current picks in `multibaggers` | 915 rows / 915 distinct symbols |
| Picks with a future `as_of_date` | 42 / 915 (4.6%), dated 2026-11-14 |
| Oldest pick `as_of_date` | 2015-05-30 |
| Pick `updated_at` | Every row has 2026-10-16 09:30:34.043063 |
| Pick provenance | All 915 say `screener_in` |
| Pick freshness labels | 870 say `live (cached within TTL)`; 45 say `live` |
| Historical `fundamentals_pit` | 27,566 rows / 2,023 distinct symbols |
| Newest historical snapshot | 2026-10-06: 821 distinct symbols |
| Existing audit outcome | 0 unwaived failures, 6 waived findings |

The 2,023 historical symbols are not necessarily the current active universe. The mismatch establishes that the latest-snapshot denominator omits historical symbols; measure active coverage against an explicit, versioned universe before interpreting the omission as a provider failure.

## Recommendations in priority order

### 1. P0 — Separate observed dates from estimated availability; reject future data

`modules/adapters/screener_in.py:456` extracts a result date, or estimates one by adding 45/60 days to quarter end. It stores both cases under `As_Of_Date` without recording whether the date was observed or estimated. `modules/pit_auditor.py:291` compares the supplied as-of date with quarter end; `modules/scoring/engine.py:124` passes these provider fields directly and does not reject an as-of date later than the scoring date. Its age calculation also treats future dates as negative ages, avoiding stale-data penalties.

The 42 future dates are confirmed. The estimated-date path is a plausible explanation, not proven row-level provenance. Investigate source payloads before changing stored dates.

Store `period_end`, `published_at`, `availability_estimated`, `fetched_at`, and `scored_at` separately. Validate that observed publication is no later than the scoring cutoff. Do not overwrite a future date with today's date. Quarantine unverifiable rows, retaining a last verified observation where available. Historical joins must select information available at the historical cutoff. Treat estimated availability explicitly as uncertainty, rather than evidence of an actual announcement.

Acceptance: zero future observed-publication dates in eligible picks; every historical score records a cutoff and the observation used.

### 2. P1 — Preserve validation failures through scoring and repeat validation

At `modules/scoring/engine.py:179`, `sanitized, _ = validate_record(...)` discards all returned DQ flags. At line 202, sanitized values are copied back only when non-null. Consequently, a validator converting an invalid input to `None` can leave the original invalid value in the scoring payload. This is a code-level propagation defect, independent of whether later factor conversion masks the error.

At `modules/data_layer/dq_gates.py:285` and `:342`, DataFrame validation clears its managed flags and checks already sanitized values again. For example, a clamped value can lose its flag and receive a higher quality score on the next pass. Record validation also skips missing values while DataFrame validation penalizes nulls, and absent columns reduce the DataFrame denominator.

Merge validation findings into scoring output, write null replacements back, and calculate quality against a fixed required-input contract. Keep immutable raw inputs and correction history; distinguish current validity from historical corrections. Weight critical missing inputs more heavily than optional fields. Out-of-range values should be quarantined or explicitly marked as corrected; unit conversion should follow provider metadata rather than magnitude alone.

Acceptance: invalid inputs cannot survive normalization; critical missing data cannot score as complete; revalidating the same observation cannot erase its correction history or inflate quality.

### 3. P1 — Measure freshness and coverage per active symbol

`modules/data_layer/data_freshness.py:387` restricts its denominator to `MAX(as_of_date)` and assigns that entire subset one age. It cannot reveal older or absent symbols outside the subset. Its exception path returns zero counts with `alert_active=False`. The current latest historical snapshot is ten calendar days old, while every current pick has today's write timestamp. These are distinct clocks and datasets.

Use an explicit active-universe version and join each symbol to its latest eligible observation. Report missing symbols, stale observations, null critical fields, and provider failures separately. Use field-appropriate freshness: trading sessions for prices, reporting periods and observed publication for fundamentals, and a separate ingestion age for cache health. Database failures should produce UNKNOWN/unavailable status and an actionable alert. Publish scan outputs with a shared `scan_id`, and gate completion on required coverage and successful persistence to the intended current/history tables.

Acceptance: fresh + stale + expired + missing equals the active-universe size; partial writes cannot appear as a complete fresh scan.

### 4. P1 — Distinguish uncomputed backtests from genuine zero returns

The current audit waives zero-fill findings for `backtest_cagr` (154/915), `backtest_max_dd` (196/915), `backtest_sharpe` (190/915), and `backtest_win_rate` (223/915). A real result can be zero, so these counts alone do not identify bad rows. The waiver text says missing computations previously used zeros.

Add `backtest_status`, observation count, period, and run ID. Store NULL for uncomputed/failed outputs. Recompute or classify legacy rows using execution evidence; do not blanket-replace zero values. Retire the waivers after verified cleanup.

Acceptance: every numeric backtest result belongs to a successful run with sufficient observations; uncomputed results remain null.

### 5. P2 — Make audit success reflect semantic quality

`modules/data_layer/dq_audit.py:116` checks only the newest write timestamp. It does not test future publication dates or per-row source age. Critical schema coverage is checked only for columns that exist, so entirely missing required columns can escape that coverage loop. Its `_spearman` implementation assigns sequential ranks to ties instead of average ranks.

Extend the existing audit with required-column assertions, future/invalid-date checks, per-symbol coverage, explicit missingness rules, score/input reconciliation, and properly tie-aware correlations. Require waivers to carry an owner, issue, expiry, affected population, and measurable exit condition. Report PASS_WITH_WAIVERS distinctly. The constant-source waiver is not evidence of corrupted data: a single configured primary provider can legitimately populate every row. Missing pledge information must remain unknown and be visible to downstream eligibility rules.

Acceptance: the observed future dates trigger a failure; missing required columns trigger a failure; audit output distinguishes clean passes from accepted unresolved issues.

### 6. P2 — Add field-level provenance and targeted source reconciliation

`modules/data_layer/data_service.py:730` labels TTL-valid cache data as live. The same orchestration can add a bhavcopy/yFinance price to another provider's fundamentals and records `price_source`, while the current picks expose a uniform `data_source`. A successful fetch establishes availability, not the financial observation's age or correctness.

Persist provider, source timestamp, units, reporting basis, fiscal period, raw-response hash, parser version, and correction lineage for important fields. Keep price and fundamentals provenance independently. Compare an independent source for a sample and high-impact disagreements, only after aligning period, units, consolidated/standalone basis, and adjustment policy. Turn disagreements into review findings rather than silently averaging mismatched inputs.

Acceptance: every displayed price and critical factor is traceable to a source observation; cache age and source age are separately visible.

## Suggested implementation sequence

1. Reject future publication dates and repair validation propagation.
2. Replace latest-snapshot freshness with active-universe coverage and explicit unavailable states.
3. Add backtest status, classify legacy results, and retire validated waivers.
4. Add field lineage, source reconciliation, and broader distribution checks.

Use focused regression cases for future dates, invalid-to-null propagation, repeated validation, missing columns, partial snapshots, database errors, and legitimate zero-valued backtests. Keep deterministic provider fixtures so these checks do not depend on live network availability.

## Follow-up: using the downloaded folders

Inspected the repository root, `multibagger-claude1-fixed`, application backups, local caches, the Parquet lake, bhavcopy folders, and listing metadata. Some root/data databases are empty or contain unrelated tables. The populated primary sources for this enrichment are under `Newmultibagger-main`:

| Local source | Observed contents | Use |
|---|---|---|
| `data/lake/daily` | 2,000 Parquet files, 24,980 historical rows, dates 2026-06-09 through 2026-08-20 | Dated fundamental reference snapshots |
| `runtime/bhavcopy_history` | 279 daily CSVs, ending 2026-10-15 | Validated equity OHLCV and latest dated closing prices |
| `runtime/bhavcopy_cache` | 13 original exchange CSVs | Price cross-checks on overlapping dates |
| `data/nse_listing_dates.csv` | 2,831 symbol records | Listing and delisting metadata |

The root `data/lake` folder is empty. Fixed `modules/data_layer/parquet/lake_manager.py` to resolve the populated application lake relative to its source file. Reads no longer create empty partition directories. Explicit custom lake paths remain supported.

Added `Newmultibagger-main/ops/enrich_from_local_data.py` and ran it offline. The output is `Newmultibagger-main/reports/local_enrichment/2026-10-16.db`, with a sibling `.summary.json`. It contains `local_enrichment` and `source_manifest` tables. Each enrichment row retains the complete original pick as JSON and adds dated local prices, listing information, the latest historical lake payload, source paths, and explicit review issues. The manifest contains SHA-256 hashes for 2,293 input files. No source database or downloaded file was modified. Scores and original prices were retained; local closes occupy separate dated columns. The application database has not been replaced with the review output.

Results:

- Validated 902,879 local equity price records across both bhavcopy folders. Selected local prices for 3,739 symbols overall.
- All 915 current picks have a local closing price. Two are older than the explicit seven-calendar-day threshold; the oldest selected close is 2026-05-14. Availability alone therefore does not establish freshness.
- Listing metadata matches 865 current picks; 50 need listing-date verification.
- Historical lake snapshots match 895 current picks.
- All 24,956 included NSE lake symbol/date keys already exist in `fundamentals_pit`; no additional NSE historical keys were discovered. This comparison establishes key overlap, not equality of all field values or independent source confirmation.
- The remaining 24 lake rows are outside the NSE symbol scope, not automatically bad data. They were excluded from this NSE price join.
- 93 picks require review: 42 future fundamental dates, 50 missing/unverified listing dates, and two stale local prices, with one overlap. The other 822 have none of these specific issues; this is not a certification that every financial input is correct.

Reproduce from the application directory with the repository Python environment:

```powershell
..\.venv\Scripts\python.exe ops/enrich_from_local_data.py --as-of 2026-10-16 --out reports/local_enrichment/another-review.db
```

The tool refuses to overwrite an existing output. It never fetches new data and never replaces financial metrics with an older snapshot. Price disagreements over 5% are review signals because observation times may differ. Prices are selected by date and equity-series priority; invalid OHLCV and conflicting closes are excluded from trusted-price selection. This output is intended for current-data reconciliation, not historical strategy evaluation using today's picks.

Verification: three offline regression tests passed, covering source preservation, original-score preservation, future dates, series priority, invalid prices, conflicting closes, future-file exclusion, exchange isolation, and lake paths independent of working directory. Focused lint and diff whitespace checks passed. The generated SQLite database passed `PRAGMA integrity_check` and coverage/date assertions. The installed Ruff version cannot parse the repository's `UP045` selector, so the focused lint check used `--isolated` with the repository's unused-import exemption.

The next data work is to obtain verified publication evidence for the 42 future-dated picks, refresh the two stale/suspended-price cases, and resolve the 50 listing matches. Reimporting the same Parquet snapshots will not address those gaps.

## Follow-up: Finding Multibagger NSE sibling project

Expanded the search to `D:\Codex\Finding Multibagger NSE\multibagger634-main`, which is outside this repository. Used that project's existing graph (3,229 nodes and 10,617 links) and current CodeGraph source to inspect its financial and price provenance. Graph vocabulary selection was `financial quality history quarterly annual sources fundamentals prices symbol master`; an inline breadth-first traversal was used without writing to the sibling folder. Database measurements supplement the graph.

The sibling `lite.db` contains 704 fundamental vectors, 3,783 annual financial rows, 7,573 quarterly rows, 612,949 normalized price rows, and an issuer master with 3,182 entries. Retained documents include NSE/BSE financial evidence, publication metadata, reporting scope, units, and source reconciliation. Its FYERS stock archive contains 1,001,552 bars starting in 2017. These are materially richer inputs than the older local Parquet projections.

Added `Newmultibagger-main/ops/import_external_data.py`. It extends the existing local review into `Newmultibagger-main/reports/local_enrichment/2026-10-16-cross-project-final.db`, with a sibling `.summary.json`, and adds these tables:

- `external_rows`: matched fundamentals, annual financials, quarters, issuer metadata and price-treatment records, preserving the source payload.
- `field_candidates`: explicitly mapped financial comparisons, current values, target missingness, normalized units, source periods, scope, identity status and field-specific evidence issues.
- `external_documents`: referenced publication and source-document metadata.
- `external_prices`: dated OHLCV from each source with separate adjustment bases and archive chunk references.
- `external_chunks` and `external_run_manifest`: retained archive lineage and extraction inputs.

Matched results against the current 915 picks:

| Result | Count |
|---|---:|
| Picks with sibling issuer-master records | 913 |
| Picks with an exact ISIN match against the local exchange download | 907 |
| Picks with sibling fundamentals and annual history | 364 |
| Picks with quarterly history | 359 |
| Annual financial rows retained | 2,222 |
| Quarterly financial rows retained | 4,515 |
| Financial field candidates | 2,266 |
| Candidates meeting the import's identity, derivation and document-availability checks for review | 2,260 |
| Candidates for currently missing target values | 170 |
| Missing-target candidates meeting those checks | 168 |
| Candidates still requiring additional source-evidence review | 6 |
| Retained source-document lookups | 2,070 |
| Normalized project price rows retained | 372,255 |
| FYERS archive price rows retained | 625,902 |

The price records cover 2017-01-02 through 2026-10-16. Source histories overlap; these counts are not additive unique market observations. They are not spliced into a single return series. The sibling project's normalized-price treatments are preserved, and FYERS retains its declared `provider_adjusted_unknown` basis.

The 168 missing-target candidates span 68 picks: CFO/PAT 38, debt/equity 8, five-year PAT CAGR 39, ROA 42, ROCE 40, and ROE 1. The external price sources also have a newer dated observation than the initial local review for 109 picks. These are concrete additions from the sibling folder, beyond merely reusing the same local Parquet keys.

Growth-unit conversion is explicit: source `sales_cagr_5y` and `profit_cagr_5y` are fractions, while current target `sales_cagr_5y` and `pat_cagr_5y` use percent. A source value of 0.17 therefore produces a 17% candidate while retaining 0.17 in the original payload. Growth evidence must cover approximately five years with at least six annual observations. No quarterly EPS growth is substituted for a differently defined long-term growth field. Other mappings preserve ratios versus percentages and retain their derivation formulas.

Field evidence is checked individually. A top-level publication date does not confer publication verification on unrelated inputs. Missing documents, future/unavailable document timestamps, missing derivation, unverified issuer identity, and incomplete growth windows remain explicit review issues. Annual and quarterly projection rows are reference history, not automatically certified historical information vintages. Existing raw financial amounts remain in their source units, documented by the retained parent financial-quality metadata; they are not silently mixed with crore-denominated fields.

The importer opens sibling databases without writes or journal creation. It rejects nonempty WAL and rejects extraction if database size/mtime or WAL changes during the read. No 7.6 GB source database copy was needed. Source-response blobs remain in the sibling database; archive response hashes and chunk metadata were retained, but original response bodies were not independently revalidated during this import.

All original 915 local review rows, original prices, and scores remain intact. The 168 missing-field candidates require target fiscal-period, reporting-scope and formula compatibility review before adoption. They are not silently substituted into live scoring, and matching issuer identity does not supply missing listing dates or fix the 42 future quarterly dates.

Reproduce from `Newmultibagger-main`, choosing a new output filename:

```powershell
..\.venv\Scripts\python.exe -m ops.import_external_data `
  --base reports/local_enrichment/2026-10-16.db `
  --external-db 'D:\Codex\Finding Multibagger NSE\multibagger634-main\lite.db' `
  --archive-db 'D:\Codex\Finding Multibagger NSE\multibagger634-main\runtime\fyers-stocks-2017-before-20261016\daily.sqlite3' `
  --out reports/local_enrichment/another-cross-project-review.db `
  --as-of 2026-10-16
```

Six offline tests passed for both enrichment utilities, including fraction-to-percent conversion, preservation of original values and scores, issuer matching, future publication exclusion, incomplete growth windows, external source mutation/WAL rejection, and the prior local-data checks. Focused lint passed. The import performs a database integrity check before publishing its output and indexes prices by symbol/date for efficient review.

Additional assertions on the completed output confirmed all 915 original review rows match the baseline exactly, no imported price date exceeds the cutoff, and every field marked usable for evidence review has an ISIN match.
