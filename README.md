# Client Acquisition Agent — V1

An AI agent that discovers local businesses, researches their online
presence, detects operational/digital gaps, and generates lead reports —
so you spend time pitching, not hunting.

V1 scope (per the project spec): **discovery + research reports only.**
No automated emailing, no proposal generation, no autonomous outreach.

**No paid API keys required.** Discovery runs on OpenStreetMap (free,
no key), and the LLM runs locally via Ollama (free, no key).

## How it works

```
OpenStreetMap search (Overpass + Nominatim)
        |
        v
Business Data Collector  (discovery/)
        |
        v
Research Agent            (research/)   -- website + social checks
        |
        v
Problem Detection          (analysis/problem_detector.py)   -- LLM
        |
        v
Solution Recommendation    (analysis/solution_recommender.py) -- LLM
        |
        v
Lead Scoring                (analysis/lead_scorer.py)  -- rule-based
        |
        v
Lead Report + Interactive Map   (reports/)
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
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull llama3.2:3b   # ~2GB download, ~3GB RAM — good fit for lighter machines
   ollama serve
   ```

   **Option B — Hosted via Groq (no local resources needed)**
   - Get a free key at https://console.groq.com
   - Set `LLM_PROVIDER=groq` and `GROQ_API_KEY=...` in `.env`

3. **Configure environment**
   ```bash
   cp .env.example .env
   # defaults work out of the box for Ollama; just make sure OLLAMA_MODEL
   # matches whatever you pulled
   ```

4. **Run it**
   ```bash
   python main.py --category restaurant --location "Dar es Salaam" --limit 10 --show-top 10
   # or free text:
   python main.py --query "restaurants in Dar es Salaam" --limit 10
   # see supported categories:
   python main.py --list-categories
   ```

   This prints lead reports to your terminal, saves them to
   `./data/leads.db`, and writes an interactive map to
   `./data/leads_map.html` — open it in any browser to see leads plotted
   and color-coded by priority (red = high, orange = medium, gray = low).

## Project structure

```
client-acquisition-agent/
├── config/settings.py         # all env/config in one place
├── discovery/                  # find businesses (OpenStreetMap)
│   ├── osm_places.py           # Overpass API + Nominatim geocoding, no key needed
│   └── models.py                # Business, WebsiteFindings, etc. (Pydantic)
├── research/                    # gather raw signal per business
│   ├── website_checker.py       # reachability, mobile-friendliness, feature signals
│   ├── reviews_analyzer.py      # stub — no OSM review data source (see notes below)
│   └── social_checker.py        # verifies social links found on OSM + the website
├── analysis/                     # turn raw signal into insight
│   ├── problem_detector.py       # LLM
│   ├── solution_recommender.py   # LLM
│   └── lead_scorer.py            # rule-based, deterministic
├── llm/
│   ├── client.py                  # swappable Ollama/Groq abstraction
│   └── prompts.py                 # every prompt template, in one place
├── reports/
│   ├── report_builder.py          # assembles + renders text lead reports
│   ├── map_builder.py             # Folium (Leaflet.js) interactive map
│   └── templates/report.md.j2
├── storage/db.py                  # SQLite persistence
├── pipeline.py                    # orchestrates the whole flow
└── main.py                        # CLI entry point
```

## Design notes

- **`llm/client.py` is the only file that knows about Ollama/Groq.**
  Every other module calls `get_llm_client().generate_json(...)`. Swapping
  models or providers later is a one-file change.
- **Discovery uses OpenStreetMap, not Google Places.** `discovery/osm_places.py`
  geocodes a location via Nominatim, then queries Overpass for businesses
  matching a category tag (restaurant, salon, pharmacy, etc. — see
  `CATEGORY_TAGS`). Both services are free and need no API key, but are
  community-run and rate-limited — be polite (the code already sleeps
  between calls and identifies itself via a real User-Agent, which you
  should personalize in `.env`).
- **Mapping uses Folium, a Python wrapper around Leaflet.js.** `reports/map_builder.py`
  produces a single self-contained HTML file with no JS to write by hand.
- **Lead scoring is rule-based, not LLM-based**, and now leans on website
  quality, social presence, and contact-info completeness (since OSM has
  no review data to draw on). Tune the point values in
  `analysis/lead_scorer.py` as you calibrate against real outcomes.
- **Reviews are a stub in V1.** OpenStreetMap is a map database, not a
  review platform, so `research/reviews_analyzer.py` returns empty
  findings. It's kept as its own module so a review data source can be
  plugged in later without touching the rest of the pipeline.
- **Social media checks are intentionally shallow.** V1 only checks
  whether a social link (found via OSM's `contact:*` tags or scraped off
  the business's own website) actually resolves. Deeper engagement
  signals need each platform's official API with business owner consent —
  a good V2 addition.
- **Website signal detection is keyword-heuristic, not a full audit.**
  Good enough to give the LLM real evidence to reason over; extend
  `FEATURE_SIGNALS` in `website_checker.py` as you learn what matters for
  your target categories.

## Next steps (post-MVP, per the spec)

Once these reports prove valuable: proposal generation, CRM integration
(store leads somewhere better than raw SQLite), and outreach automation.
Don't build these until V1's reports are actually good — that's the whole
point of scoping V1 this way.
