# Client Acquisition Agent — V3

An AI agent that discovers local businesses, researches their online
presence, qualifies leads, designs solutions, estimates costs, generates
proposal PDFs, drafts personalized outreach, and tracks the whole pipeline
through a human-approved, human-sent outreach workflow.

V1: **discovery + research reports.**
V2: **lead qualification, solution design, tech recommendation,
cost/timeline estimation, proposal PDFs.**
V3: **reachability checks, opportunity ranking, outreach drafting with
mandatory human approval, a CRM, response classification, follow-up
scheduling, a knowledge base, and a funnel dashboard.**

**The single most important rule in V3: AI discovers, AI analyzes, AI
drafts — a human approves, a human sends, a human closes.** This tool
never sends an email, WhatsApp, or LinkedIn message via any API. It only
creates drafts for you to review and sends nothing.

**No paid API keys required.** Discovery runs on OpenStreetMap (free,
no key), and the LLM runs locally via Ollama (free, no key).

## Phases of the agent's work

The agent performs its work in eight phases. Phases 1–4 are machine-driven,
phases 5–7 always pass through a human, and phase 8 feeds learning back into
future runs.

1. **Discovery** — search OpenStreetMap (Overpass + Nominatim) for
   businesses matching a category and location. No API key needed.
2. **Research** — check each business's website reachability and social
   presence, and extract contact channels (email, phone, socials).
3. **Problem detection & solution recommendation** — the LLM identifies
   digital gaps (no website, weak online presence, no reviews) and
   recommends a category-appropriate solution.
4. **Qualification, design & ranking** — score each lead, generate a
   proposal (solutions, tech stack, cost, timeline), and rank all
   opportunities by need, budget, and reachability.
5. **Outreach drafting (human approval required)** — generate a
   personalized draft for a chosen channel. It is never sent; it sits as
   `Pending Approval` until you act.
6. **Human sends & response logging** — you approve, send from your own
   account, then mark the draft sent and log the reply. The agent
   classifies the response (Warm Lead / Future Opportunity / Not
   Interested / Needs More Info / Converted) and updates the CRM.
7. **Follow-up scheduling** — leads that were contacted but did not reply
   are surfaced after a configurable delay for a follow-up draft
   (again human-approved and human-sent).
8. **Insights & reporting** — aggregate conversion stats per category into
   a knowledge base (only once enough data exists), and render a funnel
   dashboard you can export to CSV.

```
Phase 1     Phase 2     Phase 3     Phase 4
Discover  → Research  → Detect &  → Qualify,   \
             & Extract   Recommend    Design      |
  |           contacts     Solution     & Rank      |  machine-driven
  v             v            v           v          |
[database]  [database]   [database]  [proposals/]  /
                    |
                    v
             Phase 5  Draft outreach ──→ Pending Approval
                    |                        |
                    v                        v
             Phase 6  Human approves ──→ Human sends ──→ Human logs response
                                             |
                                             v
                             Phase 7  Follow-up scheduled if no reply
                                             |
                                             v
                    Phase 8  Insights / knowledge base / funnel dashboard
```

## How it works

```
                        V1 (always runs)
OpenStreetMap search (Overpass + Nominatim)
        |
        v
Business Data Collector  (discovery/)
        |
        v
Research Agent            (research/)   -- website + social checks (no LLM)
        |
        v
Presence Summary          (research/presence_summarizer.py) -- worker model
        |
        v
Problem Detection          (analysis/problem_detector.py)   -- reasoning model
        |
        v
Solution Recommendation    (analysis/solution_recommender.py) -- LLM
        |
        v
Lead Scoring                (analysis/lead_scorer.py)  -- rule-based
        |
        v
Lead Report + Interactive Map   (reports/)

                        V2 (optional, --generate-proposals)
        |
        v
Lead Qualification          (analysis/lead_qualifier.py)  -- rule-based
        |
        v
Solution Design Engine      (analysis/solution_designer.py)  -- LLM + Solution Library
        |
        v
Tech Stack Recommendation    (analysis/tech_recommender.py) -- LLM, constrained choices
        |
        v
Cost & Timeline Estimation    (analysis/cost_estimator.py)  -- deterministic
        |
        v
Proposal PDF Generation        (reports/proposal_builder.py) -- WeasyPrint PDF

                        V3 (outreach + CRM)
        |
        v
Reachability Check           (research/contact_finder.py)  -- email/channels, deterministic
        |
        v
Opportunity Ranking Engine   (analysis/opportunity_ranker.py) -- rule-based
        |
        v
Outreach Preparation         (analysis/outreach_preparer.py)  -- LLM hook
        |
        v
Outreach Drafting            (analysis/outreach_drafter.py)   -- LLM per channel
        |
        v
HUMAN APPROVAL                (CLI: approve/reject)           -- required
        |
        v
HUMAN SENDS the message themselves  (CLI: mark-sent)          -- the system never sends
        |
        v
Response Logging + Classification   (analysis/response_classifier.py) -- LLM, constrained enum
        |
        v
Follow-Up Agent                      (analysis/followup_agent.py) -- rule trigger + LLM draft
        |
        v
CRM + Knowledge Base + Funnel Dashboard  (storage/db.py, analysis/insights.py, reports/dashboard.py)
```

## Setup

1. **Install dependencies**
   ```bash 
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set up your Llama model**

   **Option A — Local via Ollama (recommended, free, private)**

   This project uses **two local models**, each loaded only for the tasks
   that need its strength (`worker` = fast/cheap; `reasoning` = stronger):
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen2.5:3b   # worker ~2GB download, ~3GB RAM (instruct build)
   ollama pull qwen2.5:7b   # reasoning ~4.7GB download, ~5-6GB RAM (instruct build)
   ollama serve
   ```
   `qwen2.5:3b` / `qwen2.5:7b` are Qwen 2.5's instruct models (the
   `-instruct`-suffixed tags are the same models under a longer name).
   Both fit in 12GB RAM alongside the OS + Python. Ollama loads a model on
   first use and keeps it resident for `OLLAMA_KEEP_ALIVE` (default `5m`)
   after the last call, so idle models release memory instead of lingering.

   **Option B — Hosted via Groq (no local resources needed)**
   - Get a free key at https://console.groq.com
   - Set `LLM_PROVIDER=groq` and `GROQ_API_KEY=...` in `.env`
   - Optional: `GROQ_WORKER_MODEL` / `GROQ_REASONING_MODEL` for role parity

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   New dual-model variables (in `.env`):
   - `OLLAMA_WORKER_MODEL` (default `qwen2.5:3b-instruct`; the included `.env`
     ships with `qwen2.5:3b`, the same instruct build)
   - `OLLAMA_REASONING_MODEL` (default `qwen2.5:7b-instruct`; the included
     `.env` ships with `qwen2.5:7b`)
   - `OLLAMA_KEEP_ALIVE` (default `5m`)
   - `REASONING_MODEL_ENABLED` (default `true`) — see phased rollout below
   - `FOLLOWUP_ESCALATION_SCORE` (default `90`)

   **Backward compatible:** a deployment that only sets the legacy
   `OLLAMA_MODEL` keeps working — when the role-specific vars above are
   unset, both roles resolve to `OLLAMA_MODEL`. Upgrade the code first, pull
   the new models, then add the role vars to switch to the dual-model setup.

   **Phased rollout** (`REASONING_MODEL_ENABLED=false`): runs the whole
   pipeline on the worker model alone — the 7B model is never pulled or
   loaded. Quality may be lower for problem detection, solution design, and
   proposal writing, but discovery → research → problem detection → scoring
   can be validated before committing to the second model. A warning is
   logged once at startup in this mode.

   **Checking RAM usage:** `python main.py model-status` prints the models
   Ollama currently has resident (equivalent to `ollama ps`).

4. **Discover businesses (V1 lead reports + map)**
   ```bash
   python main.py discover --category restaurant --location "Dar es Salaam" --limit 10 --show-top 10
   # or free text:
   python main.py discover --query "restaurants in Dar es Salaam" --limit 10
   # see supported categories:
   python main.py discover --list-categories
   ```

   (The old flat invocation `python main.py --category restaurant ...` still
   works and routes to `discover`.) This prints lead reports to your
   terminal, saves them to `./data/leads.db`, and writes an interactive map
   to `./data/leads_map.html` — open it in any browser to see leads plotted
   and color-coded by priority (red = high, orange = medium, gray = low).

5. **Generate proposals (V2 — same command, add a flag)**
   ```bash
   python main.py discover --category restaurant --location "Dar es Salaam" --limit 3 --generate-proposals
   # override minimum qualification threshold:
   python main.py discover --category hotel --location "Arusha" --limit 5 --generate-proposals --min-qualification 50
   ```

   Proposals are saved as PDFs in `./data/proposals/`.

6. **Rank opportunities (V3)**
   ```bash
   python main.py rank
   ```

7. **Draft outreach (V3) — see the human-approval workflow below**
   ```bash
   python main.py prepare-outreach --place-id node/123 --channel email
   python main.py list-drafts --status "Pending Approval"
   python main.py approve --draft-id 1
   python main.py mark-sent --draft-id 1      # records that YOU sent it
   python main.py log-response --draft-id 1 --text "We are interested."
   ```

8. **Dashboard, export & insights (V3)**
   ```bash
   python main.py dashboard
   python main.py export-dashboard --path dashboard.csv
   python main.py insights
   python main.py follow-ups
   ```

## Project structure

```
client-acquisition-agent/
├── config/settings.py         # all env/config in one place
├── discovery/                  # find businesses (OpenStreetMap)
│   ├── osm_places.py           # Overpass API + Nominatim geocoding, no key needed
│   └── models.py                # ALL Pydantic models (V1 + V2 + V3) in one place
├── research/                    # gather raw signal per business
│   ├── website_checker.py       # reachability, mobile-friendliness, feature signals
│   ├── reviews_analyzer.py      # stub — no OSM review data source (see notes below)
│   ├── social_checker.py        # verifies social links found on OSM + the website
│   ├── contact_finder.py        # V3: email/channel extraction + reachability score
│   └── presence_summarizer.py   # V3 retrofit: worker-model presence summary → problem detection
├── analysis/                     # turn raw signal into insight
│   ├── problem_detector.py       # LLM
│   ├── solution_recommender.py   # LLM
│   ├── lead_scorer.py            # rule-based, deterministic (V1)
│   ├── lead_qualifier.py         # rule-based (V2) — qualification before proposal
│   ├── solution_designer.py      # LLM + Solution Library (V2, feeds insights in V3)
│   ├── tech_recommender.py       # LLM + constrained stack validation (V2)
│   ├── cost_estimator.py         # deterministic (V2) — LLM gives labels, Python computes numbers
│   ├── opportunity_ranker.py     # V3: rule-based ranking (need + budget + reachability)
│   ├── outreach_preparer.py      # V3: LLM personalization hook
│   ├── outreach_drafter.py       # V3: LLM channel drafts, Pending Approval only
│   ├── response_classifier.py    # V3: LLM classification against a fixed enum
│   ├── followup_agent.py         # V3: rule-based trigger + LLM follow-up draft
│   └── insights.py               # V3: knowledge base (SQL aggregation, not ML)
├── solutions/                    # V2: Solution Library of package templates
│   ├── library.py                # template loader + lookup
│   └── templates/                # YAML templates by category
│       ├── restaurant.yaml
│       ├── school.yaml
│       ├── hospital.yaml
│       ├── hotel.yaml
│       └── real_estate.yaml
├── llm/
│   ├── client.py                  # the ONLY file that talks to Ollama/Groq; role-based factory
│   └── prompts.py                 # every prompt template, in one place (V1+V2+V3)
├── reports/
│   ├── report_builder.py          # assembles + renders text lead reports (V1)
│   ├── map_builder.py             # Folium (Leaflet.js) interactive map
│   ├── proposal_builder.py        # V2: proposal PDF generation via WeasyPrint
│   ├── dashboard.py               # V3: funnel metrics + ranked leads + CSV export
│   └── templates/
│       ├── report.md.j2
│       └── proposal.html.j2
├── storage/db.py                  # SQLite persistence (V1 + V2 + V3 tables)
├── pipeline.py                    # orchestrates the whole flow (V1 always, V2 optional)
├── tests/
│   └── test_opportunity_ranker.py # unit tests for the ranking engine
└── main.py                        # CLI entry point (subcommands)
```

## V2: how proposal generation works

1. **Lead Qualification** (`analysis/lead_qualifier.py`)
   - Rule-based scoring of business activity, digital presence, ability-to-pay, and solution need.
   - Leads scoring below `MIN_QUALIFICATION_SCORE_FOR_PROPOSAL` (default: 40) are skipped — no wasted LLM calls.

2. **Solution Library** (`solutions/`)
   - Pre-built package templates (restaurant, school, hospital, hotel, real estate).
   - The Solution Design Engine selects the best template and customizes features based on detected problems.
   - Categories without a template get an LLM-generated custom blueprint.

3. **Tech Stack Recommendation** (`analysis/tech_recommender.py`)
   - LLM chooses from a constrained list of allowed stacks.
   - Response is validated; falls back to default if LLM returns something outside the list.

4. **Cost & Timeline Estimation** (`analysis/cost_estimator.py`)
   - The worker model provides only a qualitative complexity label (Low/Medium/High).
   - All dollar figures and week ranges are computed deterministically from a rate table.
   - Extra features beyond the template's base features add cost.

5. **Proposal PDF** (`reports/proposal_builder.py`)
   - Rendered from a Jinja2 HTML template, converted to PDF via WeasyPrint.
   - Executive summary is the only LLM-generated text in the proposal.
   - Saved to `./data/proposals/<business_slug>.pdf`.

## V3: outreach workflow and the human-approval rule

This is the heart of V3. **The system never sends a message.** Every
outreach draft starts as `Pending Approval` and only moves forward through
explicit, individual, human CLI commands — there is no "approve all" and
no scheduling-to-send.

```
1. python main.py prepare-outreach --place-id node/123 --channel email
   → generates a personalized draft (status: Pending Approval)
2. python main.py list-drafts --status "Pending Approval"
   → review the drafts; read each one carefully
3. python main.py approve --draft-id 7      (or: reject --draft-id 7)
   → YOU approve exactly one draft at a time
4. python main.py mark-sent --draft-id 7
   → records that YOU sent it from your own email/WhatsApp/LinkedIn.
     The system did not send anything — you did. CRM marks the lead
     'Contacted' and schedules a follow-up.
5. python main.py log-response --draft-id 7 --text "We're interested."
   → classifies the reply into a fixed set: Warm Lead / Future
     Opportunity / Not Interested / Needs More Info / Converted, and
     updates the CRM.
6. python main.py follow-ups
   → lists leads Contacted > FOLLOWUP_AFTER_DAYS ago with no response.
7. python main.py prepare-outreach --place-id node/123 --channel email --followup
   → drafts a follow-up referencing the earlier message (Pending Approval
     again — same human approval flow, no exceptions).
```

Why it works this way: small Llama models sometimes invent plausible-sounding
details. That is exactly why every draft goes through a human before
anything is sent — reviewing the message is the safety step, not a formality.

## Design notes

- **`llm/client.py` is the only file that knows about Ollama/Groq.**
  Every other module calls `get_llm_client(role=...).generate_json(...)`.
  Two roles exist — `worker` (fast/cheap: extraction, summarization,
  classification) and `reasoning` (stronger: business reasoning, design,
  proposal/outreach writing) — each bound to a configured model and cached
  per role. Swapping models or providers later is a one-file change.
  `OllamaClient` sends `keep_alive` on every call and offers `unload()` to
  release a model immediately when a role is done for a while.
- **Numbers are never trusted from the LLM.** Scores, costs, and timelines
  are computed by deterministic Python functions that consume LLM-provided
  *qualitative* labels (e.g. `complexity: "Medium"`). This is a hard
  requirement — small Llama models are unreliable at producing consistent
  numeric output.
- **Discovery uses OpenStreetMap, not Google Places.** `discovery/osm_places.py`
  geocodes a location via Nominatim, then queries Overpass for businesses
  matching a category tag. Both services are free and need no API key.
- **The Solution Library is category-keyed.** If your target category
  doesn't have a template, the engine falls back to an LLM-generated
  custom solution without erroring. Add new YAML templates in
  `solutions/templates/` and map them in `solutions/library.py`.
- **Lead scoring vs qualification.** V1's `lead_scorer.py` measures "does
  this business have a digital gap" (problem-focused). V2's
  `lead_qualifier.py` measures "is this business worth pursuing as a
  client" (opportunity-focused). They serve different purposes.
- **Ability-to-pay is an estimate.** The qualification engine infers this
  from category + establishment signals (phone, website). This is the least
  reliable signal available — recalibrate it first once real outcomes are
  known.
- **Reviews are a stub in V1.** OpenStreetMap is a map database, not a
  review platform, so `research/reviews_analyzer.py` returns empty
  findings.
- **Cost constants are starting points.** The rate table in
  `analysis/cost_estimator.py` uses base costs from the Solution Library
  and a complexity multiplier. Tune these as you compare against actual
  project outcomes.
- **Outreach is never sent by the system.** V3 contains no SMTP, no
  WhatsApp Business API, no LinkedIn automation. It drafts, tracks, and
  records — the sending is always a human act outside this codebase.
- **Numbers are never trusted from the LLM** — now including rankings.
  `opportunity_ranker.py` computes a weighted final score from
  deterministic sub-scores and clips it to [0, 100]; response
  classification is validated against a fixed enum with a safe fallback.
- **The knowledge base is SQL aggregation, not a model.** `analysis/insights.py`
  counts contacted/replied/converted per category. It only feeds back into
  the solution designer when a category has `>= MIN_SAMPLE_SIZE_FOR_INSIGHTS`
  (default 5) contacted leads — small samples never influence recommendations.

## CLI reference

```bash
# V1 — discover and report
python main.py discover --category <category> --location "<location>" [--limit N] [--show-top N]
python main.py discover --query "<category> in <location>" [--limit N]
python main.py discover --list-categories
# (flat form `python main.py --category ...` still routes to discover)

# V2 — generate proposals (adds to V1 output)
python main.py discover --category <category> --location "<location>" --generate-proposals [--min-qualification N]

# V3 — outreach + CRM
python main.py rank
python main.py prepare-outreach --place-id node/123 --channel email|linkedin|whatsapp [--followup]
python main.py list-drafts [--status "Pending Approval"]
python main.py approve --draft-id N
python main.py reject --draft-id N
python main.py mark-sent --draft-id N
python main.py log-response --draft-id N --text "..."
python main.py follow-ups
python main.py dashboard
python main.py export-dashboard --path leads.csv
python main.py insights
python main.py model-status   # models currently resident in Ollama RAM (ollama ps equivalent)
```
