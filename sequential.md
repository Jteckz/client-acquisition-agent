# Task: Parallelize the Client Acquisition Agent Pipeline

## Project Location
`/home/jteckz7/Pictures/client-acquisition-agent`

## Context
This is a Python CLI application that discovers local businesses via OpenStreetMap, researches their online presence using HTTP requests, analyzes them with local LLMs (Ollama), and produces lead reports. The pipeline currently processes each business sequentially, causing 25 businesses to take 10-20 minutes. The goal is to parallelize the pipeline to reduce total execution time by 3-5x while maintaining correctness, error isolation, and the existing API contract.

## Architecture Summary
- `pipeline.py` — orchestrator, `run_pipeline()` loops over businesses sequentially at line 76
- `research/` — HTTP calls to business websites and social media (I/O-bound)
- `analysis/problem_detector.py` — reasoning LLM call (CPU/GPU-bound, ~5-15s per business)
- `analysis/solution_recommender.py` — reasoning LLM call (CPU/GPU-bound, ~5-15s per business)
- `research/presence_summarizer.py` — worker LLM call (CPU/GPU-bound, ~3-8s per business)
- `analysis/lead_scorer.py`, `analysis/lead_qualifier.py` — deterministic, instant
- `reports/report_builder.py` — Jinja2 rendering, fast
- `reports/map_builder.py` — Folium rendering, fast
- `storage/db.py` — SQLite persistence (concurrent writes require WAL mode or serialization)
- `llm/client.py` — LLM client factory with per-role caching; OllamaClient sends `keep_alive` per call
- All dependencies in `requirements.txt`, virtual env at `venv/`

## Critical Constraints

1. **SQLite is not safe for concurrent writes.** The database (`data/leads.db`) must be written serially or use WAL mode. All `save_*` functions in `storage/db.py` must be called from a single thread or use a lock.
2. **Ollama has limited concurrency.** The local LLM server can handle 2-3 concurrent requests but not 25. LLM calls must be bounded by a semaphore (max 2-3 concurrent).
3. **OSM APIs have rate limits.** Nominatim requires 1 req/sec. Overpass has fair-use limits. Discovery (geocoding + Overpass query) should remain sequential per region but can overlap with research of already-discovered businesses.
4. **The function signature of `run_pipeline()` must not change.** It returns `(list[str], list[LeadReport], str | None, list[ProposalDocument])`. Callers in `main.py` depend on this.
5. **Per-business error isolation is mandatory.** One business failing (HTTP timeout, LLM error, bad data) must NOT crash or skip other businesses. The existing `try/except` in the loop must be preserved per-business.
6. **The `research_business()` function is called from `pipeline.py` AND from `cmd_prepare_outreach` in `main.py`.** Any changes to its signature or behavior must be backward-compatible.
7. **`save_business()`, `save_crm_lead()`, `save_lead_report()`, `save_qualification_score()`, `save_reachability()` must be serialized.** They write to SQLite and cannot run concurrently without coordination.

## Required Changes

### 1. Parallelize Business Processing in `pipeline.py`

Replace the sequential `for business in businesses:` loop in `run_pipeline()` with `concurrent.futures.ThreadPoolExecutor`.

**Approach:**
- Keep the OSM discovery call sequential (it is one call per region, not per business)
- After `search_businesses()` returns the list, process all businesses in parallel using a thread pool
- Use `max_workers=min(len(businesses), 6)` to bound concurrency (6 threads handles HTTP I/O + LLM without overwhelming Ollama)
- Each thread handles ONE business end-to-end: research, problem detection, solution recommendation, scoring, qualification, reachability, report building
- Database writes within each thread must use a `threading.Lock` to serialize SQLite access
- Collect results as `(report, rendered_text, proposal_or_none)` tuples, maintaining order via a pre-allocated results list indexed by original position
- Exceptions per-business are caught inside the worker function, logged, and the business is skipped (matching current behavior)
- The map is still built after all businesses are processed (outside the thread pool)

**Pseudocode for the parallel loop:**
```python
import concurrent.futures
import threading

db_lock = threading.Lock()

def _process_one(business: Business) -> tuple[int, LeadReport, str, ProposalDocument | None] | None:
    """Process a single business. Returns (index, report, rendered, proposal) or None on failure."""
    idx = business._test_index  # set before submitting
    try:
        with db_lock:
            save_business(business)
            save_crm_lead(business.place_id)

        bundle = research_business(business)
        report = build_lead_report(bundle)

        with db_lock:
            save_lead_report(report)

        rendered = render_report(report)

        # V3 signals (deterministic, fast)
        problems = ProblemAnalysis(problems=report.problems)
        with db_lock:
            save_qualification_score(business.place_id, qualify_lead(bundle, problems))
            save_reachability(business.place_id, find_reachability(bundle))

        proposal = None
        if generate_proposals:
            proposal = _run_v2_safe(bundle, report, db_lock)

        return (idx, report, rendered, proposal)
    except Exception:
        logger.exception("Failed to process business: %s", business.name)
        return None

# Tag businesses with their index for ordering
for i, b in enumerate(businesses):
    b._test_index = i

results = [None] * len(businesses)

with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(businesses), 6)) as executor:
    futures = [executor.submit(_process_one, b) for b in businesses]
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        if result:
            idx, report, rendered, proposal = result
            results[idx] = (report, rendered, proposal)

# Unpack in original order
for r in results:
    if r is None:
        continue
    report, rendered, proposal = r
    rendered_reports.append(rendered)
    lead_reports.append(report)
    if proposal:
        proposals.append(proposal)
```

### 2. Add SQLite WAL Mode in `storage/db.py`

In `init_db()`, after creating the connection, enable WAL mode for better concurrent read performance:
```python
conn.execute("PRAGMA journal_mode=WAL")
```
This allows concurrent reads while one write is in progress. Combined with the `db_lock`, this ensures safe concurrent access.

### 3. Add LLM Concurrency Bounding in `llm/client.py`

Add a module-level `threading.Semaphore(3)` that wraps LLM calls. In `OllamaClient.generate()` and `GroqClient.generate()`, acquire the semaphore before making the HTTP call and release it after. This prevents 6+ simultaneous LLM requests from overwhelming Ollama.

```python
_llm_semaphore = threading.Semaphore(3)

class OllamaClient(LLMClient):
    def generate(self, prompt: str, system: str | None = None) -> str:
        with _llm_semaphore:
            # existing implementation
            ...
```

### 4. Maintain Result Ordering

The current code appends reports in discovery order. With `as_completed`, results come back out of order. Use a `results` list pre-sized to `len(businesses)` and place each result at its original index. After all futures complete, filter out `None` entries and extend the output lists.

### 5. Add a `--workers` CLI Flag (Optional but Recommended)

In `main.py`, add `--workers N` to the `discover` subcommand (default 6) to let users control parallelism:
```python
p_d.add_argument("--workers", type=int, default=6, help="Max parallel workers (default: 6)")
```
Pass this through to `run_pipeline()`.

### 6. Preserve All Existing Behavior

- The `run_pipeline()` function signature gains an optional `max_workers` parameter with a default of 6
- All existing CLI commands work identically
- All existing tests pass without modification (tests use mocked LLM and temp DB)
- The map is still built after all businesses are processed
- V2 proposal generation still works within the parallel loop
- `show-top` still queries the database after all writes complete

## Testing Requirements

After implementing the changes, you MUST:

### A. Run Existing Tests
```bash
cd /home/jteckz7/Pictures/client-acquisition-agent
source venv/bin/activate
python -m pytest tests/ -v
```
All 22 test files must pass. If any fail, fix the issue and re-run until all pass.

### B. Run a Live Smoke Test
```bash
python main.py discover --category restaurant --location "Dar es Salaam" --limit 5
```
Verify:
- 5 businesses are discovered and processed
- Lead reports are printed to terminal
- `data/leads.db` contains the new businesses
- `data/leads_map.html` is generated
- No Python tracebacks in output
- Execution completes in under 3 minutes (vs ~10+ minutes before)

### C. Test Error Isolation
Temporarily break one business's processing (e.g., mock a website check to raise an exception) and verify that other businesses still complete successfully. Restore the code after testing.

### D. Test Concurrent Database Access
Run the parallel pipeline and verify no `sqlite3.OperationalError: database is locked` errors occur. Check that all 5 businesses appear in the database.

### E. Performance Comparison
Time the parallel run vs a sequential run for the same 5 businesses:
```bash
time python main.py discover --category restaurant --location "Dar es Salaam" --limit 5
```
Report the speedup factor.

### F. Run the Full Test Suite Again
After all smoke tests pass, re-run the complete test suite one final time to confirm nothing is broken:
```bash
python -m pytest tests/ -v --tb=short
```

## Deliverables
1. Modified `pipeline.py` with parallel business processing
2. Modified `storage/db.py` with WAL mode
3. Modified `llm/client.py` with LLM concurrency semaphore
4. Optionally modified `main.py` with `--workers` flag
5. All existing tests passing
6. Smoke test results showing speedup
7. Brief summary of changes and performance improvement
