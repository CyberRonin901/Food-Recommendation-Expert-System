# Food Recommendation Expert System

A small web app where the user fills in a form and/or types a sentence, and gets back a ranked list of foods that match. Filtering is done by **rules** (hard constraints), ranking by a **weighted score**, and an **LLM** (local via **Ollama** or any external API such as **Google Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter**) translates the typed sentence into structured filters.

- **Backend:** Python 3.12, FastAPI, SQLite
- **Frontend:** Plain HTML + CSS + JavaScript (no framework, no build step)
- **LLM Support:** Dual-mode flexible architecture:
  - **Local LLM:** Ollama (e.g. `llama3.2`, `gemma`, `mistral`, `qwen2.5`) on your host machine — 100% private, no API key needed.
  - **External LLM:** Any cloud API (Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter, etc.) via API key and model name.
  - **Optional Layer:** The app works completely offline without any LLM configured; all rule-based filters and goals remain functional. Free-text requests fall back to a built-in keyword parser that maps high-level goals such as "weight loss" to nutrient goals like `high_protein` + `high_fiber`.
- **Packaging:** Docker + Docker Compose, or direct local Python virtual environment.
- **Dataset:** `daily_food_nutrition_dataset.csv` (651 rows cleaned & validated to 597 rows, 12 columns)

> This plan replaces the first version. That version assumed cuisine, price, ingredients, diet type and spice level. **None of those exist in this dataset**, so the project is now a *nutrition-based* food finder. See [What changed](#2-what-changed-from-the-first-plan).

## Quick start

The project can be run either **with Docker** (recommended for a zero-install containerized setup) or **manually** with Python on your machine.

### Option 1: Run with Docker

```bash
# 1. (Optional) Configure LLM settings:
cp .env.example .env

# 2. Build and launch:
docker compose up --build
```
Open **http://localhost:8000** in your browser.

### Option 2: Run Manually (Local Python)

```bash
# 1. Setup virtual environment and dependencies:
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 2. Build the SQLite database from CSV:
python backend/scripts/build_database.py --csv data/daily_food_nutrition_dataset.csv --db data/foods.db

# 3. Start the application server:
cd backend && uvicorn app.main:app --reload --port 8000
```
Open **http://localhost:8000**. See [Section 14](#14-setup-and-run) for detailed setup and LLM configuration.

---

## 1. What the user can do

1. Fill in the form: meal type, food categories, nutrient limits (e.g. protein at least 25 g, sodium at most 400 mg), words to include or exclude, and goals (e.g. "high protein").
2. Optionally type a sentence instead of (or on top of) the form, e.g. *"high protein dinner under 500 calories, no chicken"*.
3. Press **Find foods**. The page shows the top K matches, each with its nutrition values, a score, and a short "why this was picked" list.
4. If the sentence was used, the page also shows **how it was understood**, so the user can correct it.

---

## 2. What changed from the first plan

| First plan | Now | Why |
|---|---|---|
| Cuisine, price, spice level, ingredients, diet type, allergens, images | Removed | Not in the dataset. Inventing them would be fake data. |
| Allergy rule | Removed | Allergens cannot be derived from a food name. A wrong "safe" answer is worse than no feature. |
| Vegetarian filter | Replaced by *exclude words* | Cannot be derived reliably (see [section 3.3](#33-why-there-is-no-vegetarian-filter)). |
| PostgreSQL + SQLAlchemy | SQLite (built into Python), plain `sqlite3` | 597 rows. No server, no ORM. It lives inside the app container, so no separate database container is needed. |
| Chunked CSV ingestion, `COPY`, indexes | One simple build script | The file is ~650 lines. |
| React | Plain HTML + JS | As requested. FastAPI serves the files itself, so no CORS setup. |
| Local LLM (Ollama) | **Gemini API** | Team decision. Nothing to download or host, but it needs internet, an API key and quota (see [section 8](#8-llm-gemini-api)). |
| LLM writes the explanations | Explanations come from a template | The reasons are already computed, so a template is instant and cannot hallucinate numbers. |
| Manual Python setup on every machine | **Docker Compose** | Same environment for everyone; the database is created automatically at container start. |
| Cuisine/price/etc. in scoring weights | Goals based on real nutrient columns | See [section 6](#6-recommendation-logic). |
| `services/` + `engine/` + `ai/` + `database/` folders | One flat `app/` package | Fewer places to look for things. |
| Postman | FastAPI's built-in `/docs` page | Already included. |

---

## 3. The dataset

### 3.1 Columns

| CSV column | DB column | Range in data | How it is used |
|---|---|---|---|
| `Food_Item` | `name` | 593 unique names | Display, include/exclude words. Serving size is written inside the name, e.g. `Salmon (4oz grilled)` |
| `Category` | `category`, `category_main`, `category_sub` | 46 raw values, 13 main groups | Category filter (uses `category_main`) |
| `Calories (kcal)` | `calories` | 0 to 680 | Limit |
| `Protein (g)` | `protein_g` | 0 to 45 | Limit + goal |
| `Carbohydrates (g)` | `carbs_g` | 0 to 70 | Limit + goal |
| `Fat (g)` | `fat_g` | 0 to 40 | Limit + goal |
| `Fiber (g)` | `fiber_g` | 0 to 14 | Limit + goal |
| `Sugars (g)` | `sugars_g` | 0 to 60 | Limit + goal |
| `Sodium (mg)` | `sodium_mg` | 0 to 1580 | Limit + goal |
| `Cholesterol (mg)` | `cholesterol_mg` | 0 to 450 | Limit + goal |
| `Meal_Type` | `meal_type` | Raw rows: Dinner 225, Snack 181, Lunch 150, Breakfast 94, Side 1 | Meal filter |
| `Water_Intake (ml)` | `water_ml` | 0 to 500, and `0` in 501 of 651 rows | Stored, **not used** |

The 13 main category groups (row counts before cleaning): Condiment 129, Meal 116, Vegetable 76, Grain 69, Beverage 64, Protein 60, Fruit 34, Dairy 29, Dessert 27, Snack 20, Nut 14, Legume 11, Supplement 2. `category_main` is the text before the `/` in values like `Meal/Pasta` or `Protein/Fish`; `category_sub` is the part after.

There are no empty cells and no negative numbers.

### 3.2 Data problems found, and how the build script handles each

| # | Problem | Handling |
|---|---|---|
| 1 | **6 rows have an unquoted comma in the food name**, e.g. `Milk (2%, 1 cup)`. `pd.read_csv` crashes with `Expected 12 fields in line 21, saw 13`. Affected file lines: 21, 50, 235, 238, 378, 445. | Read with Python's `csv` module. If a row has 13 fields, join the first two with a comma. Any other bad row is rejected and logged. |
| 2 | **54 exact duplicate rows** | Drop them. 651 becomes **597 rows**. |
| 3 | **4 names still appear twice** after that: `Chimichurri (1 tbsp)`, `Olive Oil (1 tbsp drizzle)`, `Salami (3 slices)` (differ only in `Meal_Type`) and `Tzatziki Sauce (2 tbsp)` (differs only in `Category`) | Keep both rows. After ranking, keep only the best-scored row per name. |
| 4 | `Category` has 46 compound values | Split into `category_main` / `category_sub`. Keep the raw value too. |
| 5 | `Meal_Type = Side` appears once (`Kimchi (1/2 cup)`) | Keep. It is only reachable when no meal type is chosen. |
| 6 | **Servings are not comparable.** Values are per the serving in the name, which ranges from `1 tbsp` to a full plate, and some rows are recipe parts or garnishes (`Coffee Beans (3 garnish)`, `Garlic (1/2 clove in pesto)`). Condiments are 20.8% of the 597 cleaned rows. | See the notes below. This is a limitation to document, not something to fix. |
| 7 | 6 rows have 0 kcal (diet soda, club soda, salt, ...) | Keep. Never divide by calories anywhere. |
| 8 | About 42 rows have calories that do not match 4×protein + 4×carbs + 9×fat by more than 40% (e.g. `Margarita`, because of alcohol) | Leave the values unchanged. Log the count only. |
| 9 | 5 names contain accents (`Supplì`, `Ragù`, `sautéed`) | Add a `name_search` column: lowercase, accents removed, punctuation replaced by spaces, padded with spaces. The display name stays untouched. |

**How problem 6 affects results** (checked on the 597 cleaned rows): among the 20 lowest-calorie rows, **18 are condiments**. With condiments removed, the lowest-calorie rows are still things like `Club Soda (2 oz)`, `Celery (1/4 stalk minced)` and `Espresso (for dipping)`. So:

- Condiments are **excluded by default** (a checkbox lets the user include them).
- "Low calorie" is a **limit** (`max_calories`) but **not a ranking goal**, because ranking by it would always return garnishes.
- The form has an optional `min_calories`. A default of 50 is suggested; check the results after building and adjust.

### 3.3 Why there is no vegetarian filter

The dataset has no diet column, so it would have to be guessed from the name and category. A quick keyword test flagged 114 rows as meat or fish but:

- **missed** `Spaghetti Bolognese`, `Lasagna (1 serving meat)`, `Reuben Sandwich`, `Philly Cheesesteak`, `Biscuits and Gravy`, `Carbonara`
- **wrongly flagged** `Veggie Burger`, `Bun (hamburger)`, `Melted Butter (for lobster)`

A filter that is wrong in both directions is misleading. Users can type words in **Exclude words** (`chicken, beef, pork, fish`) instead. **Stretch goal:** hand-label an `is_vegetarian` column for the 593 unique names in a small CSV that the build script merges in.

---

## 4. Tech stack

| Part | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | The Docker image uses 3.12 |
| Web framework | FastAPI + Uvicorn | Gives an interactive `/docs` page for free |
| Validation | Pydantic | Request/response models, and checking the LLM's JSON |
| Database | SQLite via `sqlite3` | A single file, `data/foods.db`, created inside the container at start |
| Data cleaning | pandas + `csv` module | Used only by the build script |
| LLM | Local Ollama OR any External API (Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter) | Switchable via `USE_LOCAL_LLM` flag in `.env`. The app works fully even without an LLM. |
| Frontend | HTML + CSS + JS (`fetch`) | Served by FastAPI from the `frontend/` folder |
| Packaging | Docker + Docker Compose | One `app` service |
| Tests | pytest + httpx | httpx is needed for FastAPI's `TestClient` |
| Version control | Git + GitHub | |

---

## 5. Architecture

```text
   docker compose up --build
                |
                v
   +--------------------------- container "app" ----------------------------+
   |  entrypoint.sh: build_database.py (CSV -> foods.db), then start server  |
   |                                                                         |
   |   Browser: index.html + app.js                                          |
   |        |  POST /api/recommend  (form fields + optional "query")         |
   |        v                                                                |
   |   FastAPI  (main.py)                                                    |
   |        |                                                                |
   |        |-- query given? --> Gemini API --> Preferences JSON --> validate|
   |        |                    (any failure: warn, use form fields only)   |
   |        v                                                                |
   |   Merge: form values win, LLM values fill the blanks                    |
   |        v                                                                |
   |   Hard filters  ->  SQL WHERE (parameterised)        [filters.py]       |
   |        v                                                                |
   |   Goal scoring  ->  mean of percentile scores        [scoring.py]       |
   |        v                                                                |
   |   Sort, remove duplicate names, take top K                              |
   |        v                                                                |
   |   Templated "reasons"                                [explain.py]       |
   |        v                                                                |
   |   JSON response  ->  browser renders cards                              |
   +-------------------------------------------------------------------------+
```

The LLM never sees the database and never chooses foods. It only turns text into filters, so it cannot invent a food.

### Project structure

```text
food-recommender/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .gitattributes                  # forces LF line endings for *.sh (Windows fix)
├── .env.example                    # copy to .env and add your Gemini key
├── docker/
│   └── entrypoint.sh               # builds the database, then starts the server
├── data/
│   ├── daily_food_nutrition_dataset.csv
│   └── foods.db                    # generated at container start, git-ignored
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routes, serves frontend/
│   │   ├── config.py               # paths, Gemini key/model name, timeout (from env vars)
│   │   ├── schemas.py              # Preferences, request, response (the team contract)
│   │   ├── db.py                   # open SQLite, run a query
│   │   ├── filters.py              # Preferences -> WHERE clause + params
│   │   ├── scoring.py              # goals, percentile scoring, ranking
│   │   ├── explain.py              # template-based reasons
│   │   ├── llm.py                  # text -> Preferences via Gemini
│   │   └── pipeline.py             # recommend(): ties everything together
│   ├── scripts/
│   │   └── build_database.py       # CSV -> clean -> foods.db
│   ├── tests/
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── app.js
    └── style.css
```

`config.py` finds `data/` and `frontend/` relative to its own location, so the same paths work on a laptop and inside the container (where the repo sits at `/app`).

---

## 6. Recommendation logic

### 6.1 Database table

```text
foods(
  id INTEGER PRIMARY KEY,
  name TEXT, name_search TEXT,
  category TEXT, category_main TEXT, category_sub TEXT,
  meal_type TEXT,
  calories REAL, protein_g REAL, carbs_g REAL, fat_g REAL,
  fiber_g REAL, sugars_g REAL, sodium_mg REAL, cholesterol_mg REAL,
  water_ml REAL,
  pct_calories REAL, pct_protein REAL, pct_carbs REAL, pct_fat REAL,
  pct_fiber REAL, pct_sugars REAL, pct_sodium REAL, pct_cholesterol REAL
)
```

The `pct_*` columns are computed **once** by the build script:

```text
pct = (rank_min(value) - 1) / (N - 1)        # N = 597; 0 = lowest value, 1 = highest
```

Percentiles ignore outliers (sodium goes up to 1580 mg but 95% of rows are at or below 900) and need no tuning.

### 6.2 Hard filters (rules)

A food is **removed** if it breaks any filter the user set. Unset filters do nothing.

| Filter | Rule |
|---|---|
| Meal type | `meal_type = ?` |
| Categories | `category_main IN (...)` |
| Condiments | Excluded unless **Include condiments** is ticked |
| Include words | Name must contain **at least one** of the words |
| Exclude words | Name must contain **none** of the words |
| Limits | `min_calories`, `max_calories`, `min_protein`, `max_carbs`, `max_fat`, `min_fiber`, `max_sugars`, `max_sodium`, `max_cholesterol` |

Implementation rules:

- Build the SQL with `?` placeholders. **Never** paste user text into the SQL string.
- Word matching uses the padded `name_search` column: `name_search LIKE '% ham %'`. That way `ham` does not match `graham` or `hamburger`. There is no plural handling, so `egg` does not match `eggs`; the user types both (a stretch goal is simple stemming).
- A request with `min_calories` greater than `max_calories` is rejected with a 422 error.

### 6.3 Goals (soft ranking)

The user ticks zero or more goals. Each goal points at one nutrient:

| Goal | Column | Better when |
|---|---|---|
| High protein | `pct_protein` | higher |
| High fiber | `pct_fiber` | higher |
| Low carbs | `pct_carbs` | lower |
| Low fat | `pct_fat` | lower |
| Low sugar | `pct_sugars` | lower |
| Low sodium | `pct_sodium` | lower |
| Low cholesterol | `pct_cholesterol` | lower |

```text
goal_score = pct                if higher is better
goal_score = 1 - pct            if lower is better
final_score = 100 * average(goal_score of the selected goals)
```

- **No goals selected:** there is no ranking signal. Every food gets `score = null` and results are sorted alphabetically. The response includes a note saying so.
- **Ties** (very common, since at least half the rows have 0 cholesterol): sort by score, then protein (high first), then name.
- Goals are weighted equally. Per-goal sliders are a stretch goal.

### 6.4 Final steps

1. Sort, then keep one row per food name (the best-scored one).
2. Return the top `top_k` (default 10, allowed 1 to 50).
3. Also return `total_matches`, the number of foods that passed the hard filters.
4. **No matches:** return `results: []` and a warning that lists the active limits, e.g. *"No foods match. Try relaxing: min_protein (60)."* Do not return an error.

### 6.5 Reasons (template, no LLM)

Each reason is built from real values:

```text
Goal:    "High protein: 42 g (higher than 97% of foods)"
Limit:   "270 kcal, within your 500 kcal limit"
Word:    "Name contains 'beef'"
Meal:    "Listed as a Dinner food"
```

---

## 7. API

All routes are under `/api`. Open `http://localhost:8000/docs` to try them.

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/recommend` | Main endpoint |
| GET | `/api/options` | Lists meal types, main categories, goals, and min/max of each nutrient, so the form is built from real data and nothing is hard-coded in JS |
| GET | `/api/health` | `{ "status": "ok", "foods": 597, "llm_configured": true }` |

`llm_configured` only says whether a Gemini key is set. The health check never calls Gemini, so it costs no quota and stays fast (Docker calls it every few seconds).

### `POST /api/recommend`

Every field is optional. A missing or `null` field means "no filter".

```json
{
  "query": "high protein dinner under 500 calories, no chicken",
  "meal_type": "Dinner",
  "categories": ["Meal", "Protein"],
  "goals": ["high_protein"],
  "include_keywords": [],
  "exclude_keywords": ["chicken"],
  "include_condiments": false,
  "max_calories": 500,
  "min_protein": 25,
  "top_k": 10
}
```

Other limit fields: `min_calories`, `max_carbs`, `max_fat`, `min_fiber`, `max_sugars`, `max_sodium`, `max_cholesterol`.

**Which value wins:** a field set in the form beats the same field extracted from `query`. The LLM only fills fields the form left empty.

Response (**illustrative**: the `id`, `score`, `total_matches` and percentages are made up, and some nutrient fields are trimmed; the food name and its calories, protein, fat and sodium are from the dataset):

```json
{
  "interpreted": { "meal_type": "Dinner", "goals": ["high_protein"], "max_calories": 500,
                   "exclude_keywords": ["chicken"], "top_k": 10 },
  "total_matches": 11,
  "results": [
    {
      "id": 29,
      "name": "Beef Steak (6oz sirloin)",
      "category": "Protein/Meat",
      "meal_type": "Dinner",
      "calories": 270, "protein_g": 42, "fat_g": 10, "sodium_mg": 90,
      "score": 96.5,
      "reasons": [
        "High protein: 42 g (higher than 97% of foods)",
        "270 kcal, within your 500 kcal limit",
        "Listed as a Dinner food"
      ]
    }
  ],
  "warnings": []
}
```

`warnings` carries messages such as *"No Gemini API key is set, so the text query was ignored"*, *"The text query could not be processed (quota or network problem); using the form only"*, or the no-match hint.

---

## 8. LLM Layer (Local Ollama & External APIs)

**Job:** turn natural language `query` into a structured `Preferences` object. Nothing else.

The LLM never queries the database directly and never hallucinates food items. It only extracts user constraints into structured filters. If no LLM is configured or an LLM call fails, the app degrades gracefully and uses the form inputs directly.

### 8.1 Dual-Provider Architecture

The application supports two operating modes, toggled via `USE_LOCAL_LLM` in `.env`:

| Mode | Provider | Use Case | Key Environment Variables |
|---|---|---|---|
| **Local LLM** (`USE_LOCAL_LLM=true`) | **Ollama** | 100% offline, local machine, private data, zero API cost | `OLLAMA_MODEL=llama3.2`, `OLLAMA_BASE_URL=http://localhost:11434` |
| **External API** (`USE_LOCAL_LLM=false`) | **Any External LLM API** | High speed, no local GPU/CPU load needed | `EXTERNAL_API_KEY=...`, `EXTERNAL_MODEL=...`, `EXTERNAL_BASE_URL=...` |

Supported external LLM providers include:
- **Google Gemini:** `EXTERNAL_MODEL=gemini-3.8-flash` (or `gemini-2.5-flash`), `EXTERNAL_API_KEY=your_key`
- **OpenAI:** `EXTERNAL_MODEL=gpt-4o` (or `gpt-4o-mini`), `EXTERNAL_API_KEY=your_key`
- **Groq:** `EXTERNAL_MODEL=llama-3.3-70b-versatile`, `EXTERNAL_BASE_URL=https://api.groq.com/openai/v1`
- **DeepSeek:** `EXTERNAL_MODEL=deepseek-chat`, `EXTERNAL_BASE_URL=https://api.deepseek.com/v1`
- **Mistral:** `EXTERNAL_MODEL=mistral-small-latest`, `EXTERNAL_BASE_URL=https://api.mistral.ai/v1`
- **OpenRouter:** `EXTERNAL_MODEL=meta-llama/llama-3.3-70b-instruct`, `EXTERNAL_BASE_URL=https://openrouter.ai/api/v1`
- **Any OpenAI-compatible proxy or local server** (e.g. vLLM, LiteLLM, LocalAI)

### 8.2 Schema (in `schemas.py`)

```text
meal_type:          "Breakfast" | "Lunch" | "Dinner" | "Snack" | null
categories:         list of the 13 main categories
goals:              list of the 7 goals
include_keywords:   list of strings
exclude_keywords:   list of strings
include_condiments: bool
min_calories, max_calories, min_protein, max_carbs, max_fat,
min_fiber, max_sugars, max_sodium, max_cholesterol:  number >= 0, or null
top_k:              1 to 50
```

- **For Ollama:** Passed as native JSON schema constraint (`format: Preferences.model_json_schema()`), guaranteeing valid structured JSON output directly from the local model.
- **For External APIs:** Passed via Gemini's structured output schema or standard OpenAI-compatible JSON mode with system prompt schema instructions.
- Both outputs are validated strictly through Pydantic (`Preferences.model_validate_json`).

### 8.3 Error Handling and Graceful Fallback

Any LLM failure never crashes the application:
1. **Missing or empty API key:** Continues with the form inputs, displaying an informative badge/warning.
2. **Ollama connection failure / server down:** Returns a helpful notice (`"Could not connect to Ollama at http://localhost:11434. Make sure 'ollama serve' is running."`) while processing the form.
3. **Invalid JSON / Markdown wrapping:** Strips code blocks and retries once automatically.
4. **Rate limits, quota exhaustion (429), or timeout:** Intercepted with user warnings; the app continues using the structured form filters.

### 8.4 Choosing the model

Model IDs change often, so the name is an environment variable (`GEMINI_MODEL`) and is never hard-coded. On Google's pricing page on 2026-11-01, the current Flash models with a free tier included `gemini-3.8-flash`, and the Flash-Lite models included `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite`. **Confirm these names in AI Studio before using them.** The default in this plan is `gemini-3.8-flash`.

This is a simple extraction task, so a Flash-Lite model may be enough and cheaper. Do not decide by reputation: write 10 sample sentences with the expected JSON, run them against two models, and keep the cheaper one if it gets the same number right.

| Sentence | Expected |
|---|---|
| "high protein dinner under 500 calories, no chicken" | Dinner, `high_protein`, `max_calories` 500, exclude `chicken` |
| "low sodium snack with at least 5 g fiber" | Snack, `low_sodium`, `min_fiber` 5 |
| "something with salmon" | `include_keywords` = `["salmon"]` |
| "give me 3 breakfast ideas" | Breakfast, `top_k` 3 |

---

## 9. Frontend (plain HTML + JS)

FastAPI serves `frontend/` at `/`, so the page and the API share one origin and the browser only ever talks to `http://localhost:8000`.

**Form fields**

1. Free-text query (textarea)
2. Meal type (select: Any, Breakfast, Lunch, Dinner, Snack)
3. Categories (checkboxes, built from `/api/options`)
4. Goals (checkboxes)
5. Nutrient limits (number inputs; placeholders show the dataset min/max from `/api/options`)
6. Include words / Exclude words (comma-separated text)
7. Include condiments (checkbox, off by default)
8. Number of results (1 to 50, default 10)

**Result card:** name, category, meal type, calories, protein, carbs, fat, fiber, sugars, sodium, cholesterol, score, reasons.

**Page states:** loading, error message, warnings, "how I understood your request", empty result message.

**Request sketch**

```javascript
const body = collectFormValues();   // omit empty fields
const res = await fetch("/api/recommend", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
if (!res.ok) { showError(await res.json()); return; }
render(await res.json());
```

---

## 10. Implementation plan

Order matters: **after Step 4 you have a working demo.** Step 5 makes it one command for everyone. Step 6 is a bonus layer.

| Step | Work | Done when |
|---|---|---|
| 0 | Agree on `schemas.py` (Preferences, request, response) and the goal table. Commit them plus one hand-written example response. Test the `Preferences` schema against Gemini once (see section 8.1). | Everyone can code against the same shapes from day one, and you know the schema is accepted. |
| 1 | `build_database.py`: repair 13-field rows, dedupe, split categories, build `name_search`, compute `pct_*`, write `foods.db` (drop and recreate the table each run), then verify. | `foods` has **597** rows, no nulls, the 6 comma rows are present, running it twice gives the same result, and **the script exits with a non-zero code if any check fails** (so a broken database stops the container instead of serving empty results). |
| 2 | `filters.py`, `scoring.py`, `explain.py`, `pipeline.py::recommend(prefs)`. Pure Python, no web, no LLM. | The scenarios in section 11 pass in pytest. |
| 3 | FastAPI: `/api/recommend`, `/api/options`, `/api/health`, and serving `frontend/`. | Requests work from `/docs`; bad input gives a clear 422. |
| 4 | Frontend form, `fetch`, result cards, page states. | A non-technical person can use the page without help. **Demo-ready** (running locally with `uvicorn`). |
| 5 | Docker: `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `.env.example`, `.dockerignore`, `.gitignore`, `.gitattributes` (section 14). | On a machine with only Docker installed, a fresh clone plus `docker compose up --build` shows the page at http://localhost:8000, `/api/health` reports 597 foods, a recommendation works, and the container turns `healthy`. |
| 6 | `llm.py`: query to `Preferences` with Gemini, merge rule, fallback and warnings. | The 10 sample sentences are scored; the app still works with no key and with no internet. |
| 7 | README run instructions, screenshots, final test pass, demo script. | A teammate can set up from a fresh clone using only this README. |

---

## 11. Testing

**Build script**
- Row count is 597; zero null values; zero negatives.
- `Milk (2%, 1 cup)`, `Tea (Green, 1 cup)`, `Spinach (1 cup, raw)` exist with correct names and numbers.
- Running the script twice does not change the row count.
- A deliberately broken CSV makes the script exit with a non-zero code.

**Recommendation scenarios** (counts below were computed on the cleaned data, condiments excluded, no `min_calories`; if yours differ, check the cleaning rules first)

| Request | Expected |
|---|---|
| Dinner, `max_calories` 500, `min_protein` 25 | 15 matches; `Beef Steak (6oz sirloin)` (42 g protein) is among them |
| `max_sodium` 140, `min_fiber` 5 | 15 matches; includes `Raspberries (1 cup)` and `Black Beans (1/2 cup)` |
| Breakfast, `max_sugars` 10, `max_calories` 300, categories Grain/Dairy/Fruit/Protein/Nut | 31 matches |
| `min_protein` 60 | 0 matches, `results: []` with a warning, not an error |
| `max_calories` 50 and `min_protein` 20 | 0 matches |
| `min_calories` 400 with `max_calories` 200 | 422 validation error |
| `exclude_keywords` = `["ham"]` | No result has the word `ham` in its name, and `Bun (hamburger)` is **not** wrongly removed |
| Goals: `high_protein` only | Results are in descending protein order |
| No goals | `score` is null, results alphabetical, a note is returned |
| Same food name in two rows (e.g. `Salami (3 slices)`) | Appears once in the results |

**LLM:** unit tests with a *mocked* Gemini client (valid JSON, invalid JSON, wrong category, timeout, quota error, missing key). Tests must never call the real API by default. The 10 sample sentences run as an optional slow test that is skipped when `GEMINI_API_KEY` is not set.

**Docker smoke test** (run on a clean clone, ideally also on a teammate's Windows machine)

1. `docker compose up --build -d`, then wait until `docker compose ps` shows `healthy`.
2. `GET /api/health` reports 597 foods.
3. The first scenario above returns 15 matches through the running container.
4. `docker compose restart app` leaves the count at 597 (no duplicates).
5. `docker compose down`, then `docker compose up` again works.
6. With **no** `.env` file, the app starts and a text query returns a warning, not an error.

---

## 12. Suggested split for 5 people

| Member | Owns | Files |
|---|---|---|
| 1 | Data, database, container image | `build_database.py`, build tests, `db.py`, `/api/options` data, `Dockerfile`, `docker/entrypoint.sh`, `.dockerignore` |
| 2 | Hard filters | `filters.py` and its tests |
| 3 | LLM layer | `llm.py`, prompt, schema checks, mocked tests, model comparison |
| 4 | Scoring, ranking, reasons | `scoring.py`, `explain.py`, `pipeline.py` |
| 5 | API, frontend, compose | `main.py`, `frontend/`, `docker-compose.yml`, `.env.example`, Docker smoke test |

Day-one blockers are removed by committing `schemas.py`, a 20-row sample of the cleaned data, and the example response from section 7. With fewer people, merge 2 + 4 and keep 3 for last.

---

## 13. Known limitations (state these in the demo)

- Nutrition values are **per serving as written in the name**, not per 100 g, so a tablespoon of sauce and a full meal are not directly comparable.
- Some rows are recipe parts or garnishes, not foods someone orders.
- Each food has a single `meal_type`, so a "Dinner" search hides foods that would also suit lunch.
- No diet, allergy, cuisine or price information. Nothing here is medical or dietary advice.
- Word matching has no plural or synonym handling.
- `Water_Intake (ml)` is mostly 0 and unused.
- **Text queries need internet, a valid Gemini key and available quota.** The form works without them.

**Out of scope on purpose:** embeddings, vector search, RAG, React, PostgreSQL, ORMs, user accounts, a separate database container, deployment to a cloud host.

**Stretch goals, in rough order:** hand-labelled vegetarian flag; per-goal weight sliders; simple plural handling; extract a `serving` field from the name; a development override file for Compose (bind-mount `backend/` and `frontend/` and run `uvicorn --reload` so code changes need no rebuild); pin dependency versions; let Gemini rephrase the template reasons (with numbers locked to database values).

---

## 14. Setup and run

The system can be run in two ways:
1. **With Docker (recommended):** One command builds the container, initializes the database, and starts the server.
2. **Manually (without Docker):** Direct Python virtual environment on your host machine.

---

### 14.1 Configuration (`.env`)

Copy the template to create your `.env` file:

```bash
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
```

#### Mode A: Use Local Ollama (Offline, 100% Private, Free)
Make sure [Ollama](https://ollama.ai) is installed and running (`ollama serve`), then pull your preferred model (e.g. `ollama pull llama3.2` or `ollama pull gemma`):

```dotenv
USE_LOCAL_LLM=true
OLLAMA_MODEL=llama3.2

# If running manually on host:
OLLAMA_BASE_URL=http://localhost:11434

# If running inside Docker container (points to Ollama on your host):
# OLLAMA_BASE_URL=http://host.docker.internal:11434
```

#### Mode B: Use Any External LLM API (Gemini, OpenAI, Groq, DeepSeek, etc.)
Set `USE_LOCAL_LLM=false` and provide your API key and model name:

```dotenv
USE_LOCAL_LLM=false

# 1. Google Gemini (default)
EXTERNAL_API_KEY=your_gemini_api_key
EXTERNAL_MODEL=gemini-3.8-flash

# 2. OpenAI
# EXTERNAL_API_KEY=your_openai_api_key
# EXTERNAL_MODEL=gpt-4o-mini

# 3. Groq (Ultra-fast inference)
# EXTERNAL_API_KEY=your_groq_api_key
# EXTERNAL_MODEL=llama-3.3-70b-versatile
# EXTERNAL_BASE_URL=https://api.groq.com/openai/v1

# 4. DeepSeek
# EXTERNAL_API_KEY=your_deepseek_api_key
# EXTERNAL_MODEL=deepseek-chat
# EXTERNAL_BASE_URL=https://api.deepseek.com/v1

# 5. OpenRouter
# EXTERNAL_API_KEY=your_openrouter_api_key
# EXTERNAL_MODEL=meta-llama/llama-3.3-70b-instruct
# EXTERNAL_BASE_URL=https://openrouter.ai/api/v1
```

#### Mode C: No LLM (Form Only)
Leave `.env` empty or omit it. The application still starts, the SQLite database is built, and all structured form filters, goals, and scoring work normally.

---

### 14.2 Option 1: Run with Docker (Recommended)

**Requirements:** Docker Desktop (or Docker Engine with Docker Compose v2).

1. **Start the application:**
   ```bash
   docker compose up --build
   ```
2. **Open http://localhost:8000** in your browser.
   - Interactive Swagger API docs: **http://localhost:8000/docs**
   - Health check: **http://localhost:8000/api/health**

**What happens on start:**
- Docker installs dependencies into a Python 3.12-slim image.
- `docker/entrypoint.sh` runs `build_database.py`, repairing CSV anomalies, deduplicating records, calculating nutrient percentiles, and verifying all 597 rows.
- If any data validation check fails, the container aborts immediately with an error log.
- Uvicorn launches the FastAPI app serving both the API routes and the frontend interface.

**Useful Docker commands:**

| Task | Command |
|---|---|
| Start in background | `docker compose up --build -d` |
| View live logs | `docker compose logs -f app` |
| Stop container | `docker compose down` |
| Re-run tests inside container | `docker compose run --rm app pytest` |
| Open container shell | `docker compose run --rm app sh` |

---

### 14.3 Option 2: Run Manually (Local Development)

**Requirements:** Python 3.11 or 3.12.

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate              # Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Build the SQLite database from the dataset CSV:**
   ```bash
   python backend/scripts/build_database.py \
       --csv data/daily_food_nutrition_dataset.csv \
       --db data/foods.db
   ```
   *(Safe to run anytime; drops and reconstructs `foods.db` in under a second).*

4. **Launch the FastAPI application server:**
   ```bash
   cd backend && uvicorn app.main:app --reload --port 8000
   ```

5. **Open http://localhost:8000.**

6. **Run the test suite:**
   ```bash
   PYTHONPATH=backend pytest backend/tests
   ```

---

### 14.4 Configuration & Docker Files

**`docker-compose.yml`**

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - path: .env
        required: false        # the app still starts without a .env file
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 10s
```

**`.env.example`**

```dotenv
# ==============================================================================
# LLM Provider Configuration
# Set USE_LOCAL_LLM=true to use local Ollama model on the host.
# Set USE_LOCAL_LLM=false to use an external LLM API.
# ==============================================================================
USE_LOCAL_LLM=false

# ==============================================================================
# 1. Local Ollama Settings (used when USE_LOCAL_LLM=true)
# ==============================================================================
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434
# For Docker users where Ollama runs on host:
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# ==============================================================================
# 2. External LLM API Settings (used when USE_LOCAL_LLM=false)
# Works with ANY provider: Google Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter, etc.
# ==============================================================================
EXTERNAL_API_KEY=
EXTERNAL_MODEL=gemini-3.8-flash
EXTERNAL_BASE_URL=
```

- App: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Tests: `cd backend && pytest`

`requirements.txt` (unpinned to start; run `pip freeze` once the app works): `fastapi`, `uvicorn`, `pydantic`, `pandas`, `google-genai`, `pytest`, `httpx`.
