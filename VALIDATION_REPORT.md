# V1 / V2 / V3 Validation Report — Dual-Model Architecture

**Date:** 2026-08-12
**Host under test:** Intel i5-8250U (8 threads), 11 GB RAM, **no swap**, CPU-only Ollama
**Models:** `qwen2.5:3b` (worker) + `qwen2.5:7b` (reasoning), both pulled and served locally
**Provider:** Local Ollama (`LLM_PROVIDER=ollama`), discovery via OpenStreetMap (Nominatim + Overpass)

---

## 1. Executive summary

All three versions are functionally stable under the dual-model (worker + reasoning)
architecture. **167 automated tests pass** (150 pre-existing + 17 new dual-model tests),
and every phase was additionally validated **live** against real models and real
OpenStreetMap data. No phase-1-to-3 blocker bugs remain. Two fixes were applied:

1. **V2:** Solution-Library package names are now authoritative (the reasoning model can
   no longer rename a template package, e.g. it invented "Basic Digital Presence Package"
   for the Hotel template in a live run).
2. **V3:** Response classification was made more robust — enum labels are normalized
   against the fixed set with a prefix-tolerant match, and the classification prompt was
   reworded to labeled-only output to stop the 3B worker echoing "Status: description".

**Recommendation:** V3 is the production candidate **with the resource caveat below**.
On hosts with ≥12–16 GB RAM the dual-model default is fine; on this specific 11 GB / no-swap
machine the second model leaves only ~1.2 GB headroom, so use `REASONING_MODEL_ENABLED=false`
(worker-only) or a smaller reasoning model until more RAM / swap is available.

---

## 2. Test summary

| Suite | Count | Result |
|---|---|---|
| Pre-existing automated tests (22 files) | 150 | **OK** |
| New dual-model tests (`tests/test_dual_model_workflow.py`) | 17 | **OK** |
| **Total** | **167** | **OK** |

Run command:

```bash
venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

### Coverage by version

- **V1** — discovery, research (website/reviews/social), presence summary (worker),
  problem detection + solution recommendation (reasoning), deterministic scoring,
  lead report + Folium map. Covered by `test_discovery`, `test_research`,
  `test_problem_and_scoring`, `test_role_routing`, `test_e2e_pipeline`.
- **V2** — qualification (rule-based, zero LLM), solution design (reasoning + Solution
  Library), constrained tech stack, deterministic cost/timeline, proposal PDF (WeasyPrint).
  Covered by `test_solution_design_tech_cost`, `test_proposal_builder`, `test_role_routing`.
- **V3** — reachability (deterministic), opportunity ranking, personalization hook +
  channel drafts, human-approval state machine, response classification, follow-up
  escalation, CRM, insights, funnel dashboard. Covered by `test_draft_workflow`,
  `test_crm`, `test_followup_agent`, `test_response_classifier`, `test_outreach_drafting`,
  `test_opportunity_ranker`, `test_insights`, `test_dashboard`.

### Live validation (real models + real OSM data, temp DBs)

- V1 `discover` for `restaurant` near Arusha: found 1 real business; worker summary →
  reasoning problem-detection produced coherent problems ("No online presence…",
  "Lack of customer reviews…") and solutions. Score 55/Medium.
- V2 `generate_proposal` for a qualified hotel lead: package + features fetched from the
  template, constrained stack used (React/FastAPI/PostgreSQL/DigitalOcean), cost
  $2,000–$4,000 / 4–7 wk, executive summary generated, **PDF written successfully**.
- V3 `prepare-outreach` (hook + email/LinkedIn/WhatsApp drafts), `rank`, `dashboard`,
  `model-status`, and response classification all ran end-to-end against stored data.

---

## 3. Issues identified, fixes, and validation

### Issue 1 — V2 package-name drift (fixed)

- **Description:** In a live V2 run, the reasoning model returned `package_name`
  `"Basic Digital Presence Package"` for a hotel instead of the Solution Library's
  `"Hotel Digital Presence Platform"`. Features matched the template, but the package
  identity drifted, which would corrupt proposal branding and the knowledge base's
  "common converted package" aggregation.
- **Root cause:** `analysis/solution_designer.py` trusted the LLM's `package_name` verbatim
  even when a template existed, and `SOLUTION_DESIGN_PROMPT` never required keeping the
  template name.
- **Fix:** In `solution_designer.py`, when a template exists, the blueprint's
  `package_name` is set **deterministically from the template** (`template["package_name"]`);
  the LLM still customizes `features`. Only template-less (custom) designs accept an
  LLM-chosen name. This matches the project rule: *the Solution Library is category-keyed
  and numbers/properties are never trusted raw from the LLM.*
- **Validation:** New tests `SolutionLibraryAuthorityTest` (4 tests) assert the template
  name wins, an identical-name LLM response is preserved, and the no-template path still
  uses the LLM name / "Custom Solution" default. Live re-run confirmed the blueprint now
  returns `"Hotel Digital Presence Platform"` in 31 s with features customized per problem.
  Full suite green.

### Issue 2 — V3 response classification quality/robustness (fixed)

- **Description:** Live tests with the 3B worker showed two failure modes: (a) a clear
  "we want to move ahead" reply classified as `Needs More Info`; (b) the model echoed the
  choice as `"Future Opportunity: interested but not ready now"` (label + inline
  description) which the enum validator rejected, forcing the `Needs More Info` fallback.
- **Root cause:** The classification prompt embedded `"Label: description"` inline entries
  that a small model copied wholesale, and the validator required an exact match
  (`status not in RESPONSE_STATUSES`).
- **Fix:** (1) `RESPONSE_CLASSIFICATION_PROMPT` reformatted to a bare-label list with
  separate decision guidance (decisive `Converted` precedence noted) and an explicit
  "label only, no extra words" instruction. (2) `classify_response` now normalizes any
  output that *starts with* a valid label (e.g. `"Future Opportunity: …"` → `Future
  Opportunity`) before the fallback, a deterministic safety net.
- **Validation:** `test_response_classifier.py` (all 8 tests) still passes. Live results
  improved: `"Let's sign the contract…"` → `Converted`; `"…not interested right now"` →
  `Not Interested` (previously `Needs More Info`); questions → `Needs More Info`;
  enthusiastic → `Warm Lead`. A stubbornly ambiguous "send the full proposal / move
  ahead" still falls to `Needs More Info` on the 3B — see Limitations.

### Issue 3 — RAM headroom on the dual-model default (documented, no code fix)

- **Description:** Live runs show both models resident simultaneously: 3B = 2.2 GB,
  7B = 5.1 GB (**7.3 GB combined**). On this 11 GB, **no-swap** host, free memory dropped
  to ~1.2 GB during pipeline execution (start 1.34 GB → end 1.16 GB). Browser/editor
  processes outside the pipeline account for most of the rest.
- **Root cause:** Environmental (11 GB RAM, zero swap, CPU-only). Not a code bug.
- **Mitigation already in the codebase:** `REASONING_MODEL_ENABLED=false` runs the whole
  pipeline on the worker alone (validated live — reasoning calls completed via the 3B and
  the reasoning model is never instantiated, guarded by `test_worker_only_mode_never_
  instantiates_reasoning_copy`). `OLLAMA_KEEP_ALIVE` (default 5m) releases idle models.
- **Validation:** `model-status` / `/api/ps` confirm keep-alive expiry windows (~4–6 min)
  behave as designed.

---

## 4. Remaining known limitations

1. **Small model classification accuracy.** The 3B worker still misclassifies some clearly
   committed replies (e.g. "Can you send the full proposal? We want to move ahead" →
   `Needs More Info`). Enums are validated so the CRM is never corrupted, but labeled
   outcome accuracy for ambiguous wording is limited. Consider a hosted classifier or
   routing classification to the reasoning model where CRM accuracy matters.
2. **RAM on low-memory hosts.** Dual-model default needs ≥12–16 GB. On this 11 GB/no-swap
   box use worker-only mode or a smaller reasoning model.
3. **Sequential processing.** The pipeline is single-threaded and serial per business; on
   this CPU a full V1+V2 run costs ~2.5–3 min of LLM time per qualifying business. No
   parallelism or batching (acceptable for current volumes, worth revisiting for scale).
4. **V2 was not exercised live through a full qualified lead via discovery** on this run
   (the one discovered lead scored below the 40-point qualification gate, which correctly
   skipped proposals — the gate working as designed). The V2 chain was instead validated
   live on a synthetic qualified hotel lead plus the offline E2E suite.
5. **7B cold-start latency.** First reasoning call reloads ~150 s. Pre-warming with a
   keep-alive strategy or `ollama` warm-up call removes most of this.
6. **Package-name enforcement is one-way.** Features are still entirely LLM-chosen; there
   is no bound enforcing that template base-features are always present. Acceptable by
   design, but the door is open for the model to silently drop a base feature.

---

## 5. Performance comparison

Measured live on the test host (warm models unless noted).

| Stage | Model (role) | Observed wall time |
|---|---|---|
| Presence summary (V1) | 3B (worker) | ~8 s |
| Problem detection (V1) | 7B (reasoning) | ~30–50 s warm; **~159 s cold (includes load)** |
| Solution recommendation (V1) | 7B (reasoning) | ~10–20 s |
| **V1 per business** | 1 worker + 2 reasoning calls | **~73 s LLM time** (E2E incl. discovery: 82 s) |
| Solution design (V2) | 7B (reasoning) | 31 s |
| Complexity label (V2) | 3B (worker) | ~8 s |
| Tech stack (V2) | template default → **0 LLM calls** | ~0 s |
| Executive summary (V2) | 7B (reasoning) | ~20 s |
| **V2 proposal per qualified lead** | 2 worker + 2–3 reasoning calls | **~81 s** |
| Personalization hook (V3) | 7B (reasoning) | 27 s |
| Channel draft (V3) | 7B (reasoning) | 24–33 s (linkedin/whatsapp/email) |
| **V3 draft (hook + draft)** | 2 reasoning calls | **~60 s** |
| Response classification (V3) | 3B (worker) | 12–17 s |

Throughput: 3B ≈ 6.8 tok/s, 7B ≈ 2.8 tok/s (CPU-only).

**Relative cost per business across versions** (LLM calls): V1 ≈ 3 calls; adding V2 adds
≈ 3–4 calls (0 tech-stack calls when a template default matches); each V3 outreach draft
adds ≈ 2 reasoning calls and each logged response ≈ 1 worker call. The deterministic
wins — scoring, qualification, ranking, cost/timeline, reachability — add **zero** LLM
calls by design.

---

## 6. Verdict

| Version | Status | Notes |
|---|---|---|
| **V1** | **Production-ready** | Performs stably on both local models; live runs correct; lowest cost. |
| **V2** | **Production-ready after fix** | Package-name drift fixed; PDF generation verified; qualification gate confirmed. |
| **V3** | **Production-ready with resource caveat** | Full human-approval workflow verified; classification hardening applied; requires RAM budget for dual models (see limitation 2). |

**Recommendation:** Adopt **V3** (it is a superset of V1+V2 with identical guards) on
hardware meeting the 12–16 GB RAM recommendation. On this 11 GB / no-swap host, deploy in
worker-only mode (`REASONING_MODEL_ENABLED=false`) or with a smaller reasoning model until
RAM/swap is added. Re-run `venv/bin/python -m unittest discover -s tests -p "test_*.py"`
(167 tests) after any model-or-prompt change.