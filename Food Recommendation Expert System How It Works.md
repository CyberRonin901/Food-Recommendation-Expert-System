# Food Recommendation Expert System: How It Works

## 1. Overview

The project is a nutrition-based food finder: the user sets filters, goals, or types a sentence, and the system returns a ranked list of foods from a cleaned 597-row dataset, each with a plain-language reason. It is an expert system because the decisions come from explicit rules and a transparent scoring formula, not from a model's guess. AI sits only at the input end, turning free text into structured filters.

The flow has five parts, and only one of them uses an LLM.

| Part | File | Job | Uses AI? |
| --- | --- | --- | --- |
| Interface | `index.html`, `app.js` | Collects the form and optional sentence, shows result cards | No |
| Language understanding | `llm.py` | Converts the sentence into a structured `Preferences` object | Yes (Ollama or an external API) |
| Hard filters | `filters.py` | Removes every food that breaks a rule, as a parameterised SQL `WHERE` | No |
| Goal scoring | `scoring.py` | Ranks the survivors by percentile-based nutrient goals | No |
| Explanation | `explain.py` | Writes the "why this was picked" lines from real values | No |

The LLM never sees the database and never picks a food, so it cannot invent one. If no LLM is configured, the form, rules, scoring and explanations all still work.

## 2. Architecture and request lifecycle

Every request runs one fixed pipeline, and the LLM branch is the only AI step, running only when the user typed a sentence.

&#91;embedded content: request lifecycle · 7 steps, 1 AI branch\]

If the LLM branch fails or is not configured, the pipeline carries on with the form alone, so the user still gets results. Everything from the merge step down is deterministic. The app is served by one container: on start, `entrypoint.sh` builds the database from the CSV, then launches Uvicorn, which serves both the API and the plain HTML, CSS and JavaScript frontend from the same origin.

## 3. The knowledge base: dataset and cleaning

The system's knowledge is one CSV of 651 foods (12 columns: name, category, meal type, eight nutrients, water). A build script, `build_database.py`, cleans it into a SQLite table of 597 rows and verifies the result; if any check fails it exits non-zero and the container refuses to start, so the app never serves a broken database.

| Problem in the raw data | Count | What the build script does |
| --- | --- | --- |
| Unquoted comma in the food name, e.g. `Milk (2%, 1 cup)` | 6 rows | Reads with Python's `csv` module; a 13-field row has its first two fields joined back into the name |
| Exact duplicate rows | 54 rows | Dropped, which takes 651 rows to 597 |
| Same name still appearing twice (e.g. `Salami (3 slices)`) | 4 names | Both kept; after ranking, only the best-scored row per name is shown |
| Compound category like `Meal/Pasta` | 46 values | Split into `category_main` (13 groups) and `category_sub` |
| Accents and punctuation in names (`Ragù`, `sautéed`) | 5 names | A `name_search` column: lowercase, accents removed, punctuation to spaces, padded with spaces |
| Condiments and garnishes distort rankings | 20.8% of rows | Excluded by default; the user can tick a box to include them |

**Percentile columns.** Raw nutrient values are hard to combine: sodium reaches 1580 mg while 95% of foods sit at or below 900 mg. So the script precomputes a percentile for every nutrient once, stored in `pct_*` columns, where 0 means the lowest value in the dataset and 1 the highest.

```latex
pct = \frac{\operatorname{rank}_{\min}(value) - 1}{N - 1}, \quad N = 597
```

Percentiles are robust to outliers and need no tuning, which is why every goal in the next section can be scored on the same 0 to 1 scale.

## 4. How a food is recommended

A food reaches the user in four steps: rules remove what is not allowed, a score ranks what is left, duplicates are collapsed, and a template explains each pick. All four steps are deterministic, so the same request always gives the same answer.

### Step 1: Hard filters (rules)

A food is removed if it breaks any filter the user set; unset filters do nothing. The filters become one parameterised SQL `WHERE` clause with `?` placeholders, so user text is never pasted into the query.

| Filter | Rule |
| --- | --- |
| Meal type | `meal_type` equals the chosen value |
| Categories | `category_main` is in the chosen list |
| Condiments | Excluded unless "Include condiments" is ticked |
| Include words | Name contains at least one of the words |
| Exclude words | Name contains none of the words |
| Nutrient limits | `min_calories`, `max_calories`, `min_protein`, `max_carbs`, `max_fat`, `min_fiber`, `max_sugars`, `max_sodium`, `max_cholesterol` |

Word matching uses the padded `name_search` column, so `ham` matches a name containing the word ham but not `hamburger` or `graham`. A request where `min_calories` exceeds `max_calories` is rejected with a 422 error.

### Step 2: Goal scoring (soft ranking)

The user ticks zero or more goals, and each goal points at one nutrient's percentile column.

| Goal | Column | Better when |
| --- | --- | --- |
| High protein | `pct_protein` | higher |
| High fiber | `pct_fiber` | higher |
| Low carbs | `pct_carbs` | lower |
| Low fat | `pct_fat` | lower |
| Low sugar | `pct_sugars` | lower |
| Low sodium | `pct_sodium` | lower |
| Low cholesterol | `pct_cholesterol` | lower |

For a "lower is better" goal the percentile is flipped, then the selected goals are averaged with equal weight:

```latex
goal\_score = \begin{cases} pct & \text{higher is better} \\ 1 - pct & \text{lower is better} \end{cases} \qquad final\_score = 100 \times \operatorname{mean}(goal\_score)
```

Two design choices matter here. "Low calorie" is a limit but deliberately not a goal, because ranking by it would return garnishes and condiments. And if no goal is selected there is no ranking signal, so every score is null and results are sorted alphabetically, with a note saying so.

### Step 3: Ranking and output

1. Sort by score, breaking ties by protein (high first), then by name. Ties are common because at least half the rows have 0 cholesterol.
2. Keep one row per food name, the best-scored one.
3. Return the top `top_k` (default 10, allowed 1 to 50) plus `total_matches`, the count that passed the filters.
4. If nothing matches, return an empty list and a warning naming the active limits, for example "No foods match. Try relaxing: min\_protein (60)." This is not an error.

### Step 4: Reasons (template, no LLM)

Each result carries reasons built from its real values, such as "High protein: 42 g (higher than 97% of foods)", "270 kcal, within your 500 kcal limit", or "Listed as a Dinner food". A template is instant and cannot hallucinate a number.

## 5. Where AI is used

AI does exactly one job in this system: it turns the user's typed sentence into a structured `Preferences` object. Everything after that, from filtering to scoring to explaining, is rule-based. This is a deliberate boundary, because an LLM that chose foods could invent items or quote wrong nutrition numbers.

### What the LLM does

Given a sentence like "high protein dinner under 500 calories, no chicken", the LLM fills the same fields the form has: meal type, categories, goals, include and exclude words, the nine nutrient limits, and the number of results. It never sees the database.

| Sentence | Extracted preferences |
| --- | --- |
| "high protein dinner under 500 calories, no chicken" | Dinner, `high_protein`, `max_calories` 500, exclude `chicken` |
| "low sodium snack with at least 5 g fiber" | Snack, `low_sodium`, `min_fiber` 5 |
| "something with salmon" | `include_keywords` = salmon |
| "give me 3 breakfast ideas" | Breakfast, `top_k` 3 |

### Two ways to run it

A single flag, `USE_LOCAL_LLM`, switches the provider, and the rest of the app does not change.

| Mode | Provider | Good for |
| --- | --- | --- |
| Local (`USE_LOCAL_LLM=true`) | Ollama on the host, e.g. `llama3.2` | Fully offline, private, no API key or cost |
| External (`USE_LOCAL_LLM=false`) | Any API: Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter or an OpenAI-compatible server | Speed, and no load on the local machine |

The model name is an environment variable and never hard-coded, because model IDs change often. The plan is to run 10 sample sentences against two models and keep the cheaper one if it extracts the same number correctly.

### How the LLM is kept under control

1. **Constrained output.** Ollama receives the `Preferences` JSON schema as a format constraint; external APIs use structured output or JSON mode with schema instructions.
2. **Strict validation.** Whatever comes back is checked with Pydantic (`Preferences.model_validate_json`), so a wrong category or negative number is rejected before it reaches the filters.
3. **Merge rule.** A value set in the form always beats the same value from the sentence; the LLM only fills blanks.
4. **Shown back to the user.** The page displays "how I understood your request", so a misreading can be corrected.

### When the LLM is missing or fails

The app degrades instead of crashing. With no key, a down Ollama server, a rate limit (429), or a timeout, the user sees a warning and the form filters still run. Output wrapped in Markdown code fences is stripped and retried once. Without any LLM, a built-in keyword parser still maps high-level goals such as "weight loss" to the nutrient goals `high_protein` and `high_fiber`.

## 6. How this maps to a classic expert system

The project follows the standard expert-system layout: a knowledge base of facts and rules, an inference step that applies the rules to the user's situation, an explanation facility, and a user interface. The AI component is added in front, as a natural-language layer that feeds the inference step; it is not the reasoner.

| Expert-system component | In this project | Where |
| --- | --- | --- |
| Facts (knowledge base) | 597 cleaned foods with nutrients, categories, meal types and percentile columns | `foods.db` |
| Rules (knowledge base) | Hard filters (meal, category, words, nutrient limits, condiment exclusion) and the goal table that maps each goal to a nutrient and a direction | `filters.py`, `scoring.py` |
| Working memory | The merged `Preferences` object for this request, then the set of foods that survived the filters | `schemas.py`, `pipeline.py` |
| Inference engine | Starts from the user's facts, fires the rules against the knowledge base, and ends with a ranked list. It is data-driven (forward) reasoning with score-based conflict resolution; there is no rule chaining | `pipeline.py::recommend()` |
| Explanation facility | Per-food reasons from real values, the "how I understood your request" panel, and warnings that name the limits blocking a search | `explain.py`, response `interpreted` and `warnings` |
| Knowledge acquisition | Cleaning the CSV, computing percentiles, deciding which rules are safe to include (no vegetarian or allergy filter, because names cannot support them reliably) | `build_database.py` |
| User interface | Form plus optional free-text sentence | `frontend/` |
| AI layer (added) | LLM that converts the sentence into `Preferences`, with a keyword-parser fallback | `llm.py` |

### Why AI is kept at the edge

An expert system has to be explainable, repeatable and checkable, and an LLM is none of these when it makes the decision. So the split is:

- **AI interprets.** It handles messy human language, which rules are bad at.
- **Rules decide.** Every food in the output passed explicit filters, and its rank comes from a published formula.
- **Templates explain.** Each reason quotes a number that is in the database.

This also makes the system testable. Scenarios have fixed expected counts, for example Dinner with `max_calories` 500 and `min_protein` 25 returns 15 matches and includes `Beef Steak (6oz sirloin)`. The LLM tests use a mocked client, so no test calls a real API.

### Planned step towards a fuller expert system

Today the rules live inside Python code (`filters.py`, `scoring.py`). The natural upgrade is to move them into an explicit rule base, such as a YAML file, that the inference engine reads and that the explanation facility can cite by rule name. That would let the system answer "which rules fired" directly, and let rules change without editing code.

## 7. Worked example

Typing "high protein dinner under 500 calories, no chicken" into the sentence box, with the form left empty, produces a ranked list of high-protein dinners, which can include `Beef Steak (6oz sirloin)`. Here is the path that gets it there.

1. **Request.** The browser sends the sentence to `POST /api/recommend`.
2. **Interpretation (AI).** The LLM returns structured preferences: meal type Dinner, goal `high_protein`, `max_calories` 500, exclude word `chicken`. Pydantic validates them.
3. **Merge.** The form is empty, so the LLM's values are used. Had the form set a different meal type, the form would have won.
4. **Hard filters (rules).** Keep only foods listed as Dinner, at or under 500 kcal, not condiments, and whose name does not contain the word chicken.
5. **Scoring.** The goal is high protein, so each survivor's score is 100 times its protein percentile.
6. **Ranking.** Sort by score, break ties by protein then name, keep one row per name, and take the top 10.
7. **Explanation (template).** Each result gets reasons built from its own values.
8. **Response.** The page receives the "how I understood" summary, the cards, and any warnings.

An example card looks like this. The food name, calories, protein, fat and sodium come from the dataset; the score and percentage are illustrative.

| Field | Value |
| --- | --- |
| Food | `Beef Steak (6oz sirloin)`, Protein/Meat, Dinner |
| Nutrition | 270 kcal, 42 g protein, 10 g fat, 90 mg sodium |
| Reason 1 | High protein: 42 g (higher than 97% of foods) |
| Reason 2 | 270 kcal, within your 500 kcal limit |
| Reason 3 | Listed as a Dinner food |

If the LLM is unavailable, step 2 is skipped with a warning and only the form's filters run, so the user always gets an answer.

## 8. Design decisions and known limitations

The main design choice was to trade features the data cannot support for answers the user can trust, and the limitations below follow from the dataset itself.

### Decisions and why

- **No vegetarian or allergy filter.** Neither can be derived reliably from a food name: a keyword test misses `Spaghetti Bolognese` and wrongly flags `Veggie Burger`. A wrong "safe" answer is worse than no feature, so users type exclude words instead.
- **Percentiles, not raw values.** They ignore outliers and put every goal on one 0 to 1 scale.
- **Condiments off by default, and no "low calorie" goal.** Otherwise garnishes dominate the top of the list: 18 of the 20 lowest-calorie rows are condiments.
- **Template explanations, not LLM-written.** The reasons are already computed, so a template is instant and cannot hallucinate numbers.
- **Form beats sentence.** The user's explicit choices are never overridden by the LLM's reading.
- **LLM is optional.** The app works fully offline with the form alone.

### Limitations to state in the demo

- Nutrition values are per serving as written in the name, not per 100 g, so a tablespoon of sauce and a full meal are not directly comparable.
- Some rows are recipe parts or garnishes rather than foods someone orders.
- Each food has one meal type, so a Dinner search hides foods that would also suit lunch.
- There is no diet, allergy, cuisine or price data, and nothing here is medical or dietary advice.
- Word matching has no plural or synonym handling, so `egg` does not match `eggs`.
- `Water_Intake (ml)` is 0 in 501 of 651 rows, so it is stored but unused.
- Goals are weighted equally, and text queries need a working LLM.

Listed stretch goals include a hand-labelled vegetarian flag, per-goal weight sliders, simple plural handling and a serving-size field extracted from the name.

---

## 9. Internal Working of the Expert System

This section explains how the system processes a user's request, applies its knowledge and rules, and ultimately recommends suitable food items.

The system follows a hybrid architecture in which a Large Language Model (LLM) handles natural-language understanding, while a deterministic rule-based inference engine handles the actual recommendation process.

### 9.1 User Input and Preference Acquisition

The recommendation process begins when the user interacts with the frontend. The system accepts preferences through two complementary input methods:

**1. Structured Input (Form-Based)**

The user can explicitly specify:
- Meal type: Breakfast, Lunch, Dinner or Snack.
- Food categories: Protein, Vegetable, Grain, Fruit, Dairy, etc.
- Nutritional goals: High protein, high fiber, low carbohydrates, low fat, low sugar, low sodium or low cholesterol.
- Nutritional constraints: Minimum or maximum calories, protein, fiber, carbohydrates, fat, sugars, sodium and cholesterol.
- Include and exclude keywords to specify food names.
- Whether condiments should be included.
- Number of recommendations required (Top K).

**2. Natural Language Input**

Instead of manually selecting every preference, the user can describe their requirements in ordinary language.

For example:

"Suggest high-protein dinner options under 500 calories without chicken."

The system uses its AI layer to understand this sentence and convert it into the same structured preference representation used by the form.

Both input methods ultimately produce a common `Preferences` object, ensuring that the recommendation engine does not need separate processing logic for natural-language and form-based requests.

### 9.2 Knowledge Base Construction

An expert system requires a knowledge base containing the facts and information on which its decisions are based.

In this project, the knowledge base is constructed from a food nutrition dataset containing 651 records and 12 columns.

The dataset contains information such as:

- Food name.
- Food category.
- Meal type.
- Calories.
- Protein.
- Carbohydrates.
- Fat.
- Fiber.
- Sugars.
- Sodium.
- Cholesterol.
- Water intake.

Before the data can be used by the inference engine, it passes through a preprocessing and validation stage.

The `build_database.py` script performs the following operations:

1. Repairs malformed CSV records containing unquoted commas in food names.
2. Removes 54 exact duplicate records, reducing the dataset from 651 to 597 records.
3. Splits compound categories into main and subcategories.
4. Normalizes food names by converting them to lowercase, removing accents and replacing punctuation for reliable keyword matching.
5. Computes percentile values for nutritional attributes.
6. Stores the cleaned records and calculated values in an SQLite database.

The resulting database acts as the factual knowledge base of the expert system.

**Why are percentiles stored in the knowledge base?**

Nutritional attributes have different units and numerical ranges. For example, calories are measured in kcal, sodium in mg and protein in grams.

Directly comparing these values is not meaningful. Therefore, the system calculates a percentile for each nutrient:

`percentile = (rank_min(value) - 1) / (N - 1)`

Here, N represents the total number of cleaned food records (597).

Each food receives a percentile between 0 and 1 for every nutritional attribute. A percentile of 0 represents the lowest value, while 1 represents the highest value in the dataset.

These precomputed values allow the inference engine to compare different nutritional goals on a common scale.

### 9.3 Rule Base: Representing Expert Knowledge

The rule base contains the conditions and decision logic used to determine which foods are suitable for a particular request.

Instead of allowing an LLM to independently decide which food is healthy or appropriate, the project uses explicitly defined rules based on the available nutritional data.

The rules are divided into two categories.

**A. Hard Constraints (Filtering Rules)**

These rules determine whether a food is eligible for recommendation.

A food is rejected if it violates any explicitly selected constraint.

Examples:

- IF the requested meal type is Dinner, THEN only consider foods whose `meal_type` is Dinner.
- IF the user selects a maximum calorie limit of 500, THEN reject foods with more than 500 calories.
- IF the user requests at least 25 g of protein, THEN reject foods containing less than 25 g of protein.
- IF the user excludes chicken, THEN reject foods whose names contain the excluded keyword.
- IF condiments are not enabled, THEN exclude condiment-category records.

These conditions are translated into parameterized SQL queries and executed against the SQLite knowledge base.

The purpose of these rules is to establish eligibility. A food that violates a hard constraint cannot be recommended, regardless of its nutritional score.

**B. Soft Constraints (Preference-Based Ranking Rules)**

Not every preference needs to eliminate a food. Some preferences indicate that certain foods should be considered better than others.

For this purpose, the system uses nutritional goals as soft constraints.

The following rules are defined:

| User goal | Knowledge-base attribute | Preferred direction |
|---|---|---|
| High protein | `pct_protein` | Higher |
| High fiber | `pct_fiber` | Higher |
| Low carbohydrates | `pct_carbs` | Lower |
| Low fat | `pct_fat` | Lower |
| Low sugar | `pct_sugars` | Lower |
| Low sodium | `pct_sodium` | Lower |
| Low cholesterol | `pct_cholesterol` | Lower |

For example:

IF the user selects High Protein, THEN foods with higher protein percentiles should receive higher scores.

IF the user selects Low Sodium, THEN foods with lower sodium percentiles should receive higher scores.

These rules do not eliminate foods. They determine their relative ranking after hard filtering.

### 9.4 Inference Engine: Applying the Rules

The inference engine is responsible for applying the rule base to the facts stored in the knowledge base.

In this project, the inference engine is implemented through the recommendation pipeline (`pipeline.py`), which coordinates the filtering, scoring and ranking modules.

The process works as follows:

1. The engine receives the user's validated `Preferences` object.
2. It retrieves the available food records from the SQLite database.
3. It applies all active hard constraints to eliminate unsuitable records.
4. It calculates a preference score for every remaining food.
5. It sorts the foods according to their scores.
6. It removes duplicate food names.
7. It returns the requested Top K recommendations.

The system uses data-driven forward reasoning: it starts with the user's known preferences and applies the rules to the available food records to derive the recommendation set.

There is no rule chaining. The output of one filtering operation does not generate new rules; instead, the surviving records proceed to the scoring stage.

### 9.5 Conflict Resolution and Recommendation Scoring

A user may specify multiple goals simultaneously, and these goals may favor different foods.

For example, a user might request both high protein and low fat. One food may have excellent protein content but relatively high fat, while another may have lower fat but less protein.

The system resolves this preference conflict using a percentile-based scoring mechanism.

For every selected goal:

- If higher values are preferred, the original percentile is used.
- If lower values are preferred, the percentile is inverted using `1 - percentile`.

The final score is calculated as:

`Final Score = 100 × Average(Adjusted Goal Scores)`

For example, suppose a food has:

- Protein percentile = 0.90
- Fat percentile = 0.30

The user selects High Protein and Low Fat.

The adjusted scores become:

- High Protein = 0.90
- Low Fat = 1 - 0.30 = 0.70

Therefore:

`Final Score = 100 × (0.90 + 0.70) / 2 = 80`

The food receives a score of 80 out of 100.

All selected goals receive equal weight. The system therefore uses an equal-weight multi-criteria decision-making approach.

If no goals are selected, the system does not have a preference-based ranking signal. In that situation, scores are set to null and the results are returned alphabetically.

After scoring, foods are sorted by:
1. Final score in descending order.
2. Protein content in descending order when scores are equal.
3. Food name alphabetically when both previous values are equal.

The system then retains only the best-scored record for each unique food name and returns the requested number of results.

**Important distinction:** A high score represents how well a food matches the selected goals relative to the dataset. It does not represent an absolute measure of healthiness.

### 9.6 Explanation Facility

An important property of an expert system is its ability to explain why it reached a particular conclusion.

This project implements an explanation facility through the `explain.py` module.

Instead of asking an LLM to generate explanations, the system constructs them using predefined templates and actual database values.

For example, a recommended food might have the following explanations:

- "High protein: 42 g (higher than 97% of foods)."
- "270 kcal, within your 500 kcal limit."
- "Listed as a Dinner food."

The explanation facility makes the recommendation process transparent by showing which nutritional goals and constraints contributed to the selection.

The system also displays the interpreted preferences so users can verify how their natural-language request was understood.

Warnings are generated when no foods satisfy the requested constraints, helping users identify which limits might need adjustment.

---

## 10. Role of Artificial Intelligence in the Expert System

The project uses Artificial Intelligence to make the expert system accessible through natural language while preserving the reliability and transparency of rule-based decision-making.

The LLM is not the recommendation engine. It acts as an intelligent input-processing component that converts human language into structured knowledge that the inference engine can understand.

### 10.1 Natural Language Understanding

Users do not always express their requirements in a predefined format.

For example, the following requests express similar nutritional preferences:

- "I want something rich in protein."
- "Suggest a protein-heavy meal."
- "Find foods that help me increase my protein intake."

A traditional rule-based keyword parser would require manually defining multiple expressions and variations.

The LLM provides a more flexible way to interpret these requests.

When a user submits a sentence, the system sends it to the configured LLM provider along with instructions and the expected `Preferences` schema.

The model identifies the relevant information and produces structured JSON.

For example:

**User input:**

"Suggest high-protein dinner options under 500 calories without chicken."

**LLM interpretation:**

```json
{
  "meal_type": "Dinner",
  "goals": ["high_protein"],
  "max_calories": 500,
  "exclude_keywords": ["chicken"]
}
```

The structured output is validated using Pydantic before being passed to the recommendation pipeline.

This allows natural-language input to interact with the same rules and inference mechanism as the structured form.

### 10.2 Structured Output and Validation

LLMs can produce incorrect or unexpected responses. Passing unrestricted generated text directly into the recommendation engine would make the system unreliable.

To prevent this, the project uses structured output generation.

The `Preferences` Pydantic model defines the expected fields, their data types and validation constraints.

The model's JSON schema is provided to the LLM:

- Ollama receives the schema through its structured-output format constraint.
- External providers use structured output or JSON mode with schema instructions.

After receiving the response, the application validates it using Pydantic.

This ensures that the extracted preferences conform to the application's expected structure before they are used by the inference engine.

### 10.3 Integration of AI and Rule-Based Reasoning

The most important architectural decision is the separation between language understanding and decision-making.

The LLM is responsible for interpreting the user's intent, whereas the inference engine is responsible for deciding which foods satisfy the request.

The integration follows this sequence:

1. The user submits a natural-language request.
2. The LLM extracts the relevant preferences.
3. Pydantic validates the generated structured output.
4. The system merges the extracted preferences with the form inputs.
5. Explicit form values take priority over values extracted by the LLM.
6. The inference engine applies the hard constraints.
7. The scoring engine ranks the eligible foods.
8. The explanation facility generates reasons for each recommendation.

This separation ensures that the LLM cannot bypass the rules or directly introduce food items into the results.

Even if the LLM incorrectly interprets a request, its output must pass validation and the resulting preferences must still go through the deterministic recommendation pipeline.

### 10.4 Hybrid AI Architecture

The project combines two different approaches to artificial intelligence and decision-making:

| Component | Approach | Responsibility |
|---|---|---|
| Natural-language understanding | Large Language Model | Understands user intent and extracts preferences |
| Knowledge base | Dataset and SQLite | Stores factual food and nutrition information |
| Rule base | Explicit IF-THEN-style conditions | Defines eligibility and nutritional preferences |
| Inference engine | Rule-based reasoning and numerical scoring | Filters and ranks foods |
| Conflict resolution | Equal-weight multi-criteria scoring | Resolves competing nutritional goals |
| Explanation facility | Template-based reasoning | Explains the recommendation |
| Fallback mechanism | Keyword-based parsing or structured form input, depending on the implemented configuration | Supports operation when the LLM is unavailable |

This makes the application a hybrid AI expert system: it combines the language-understanding capabilities of modern LLMs with the explainability, consistency and controlled decision-making of a traditional rule-based expert system.

### 10.5 Why Not Let the LLM Recommend Foods Directly?

Allowing an LLM to directly generate food recommendations would introduce several problems:

1. **Hallucination:** The model could recommend foods that do not exist in the dataset.
2. **Incorrect nutritional values:** It could generate nutrition information that does not match the stored records.
3. **Inconsistent decisions:** The same request could produce different recommendations across multiple calls.
4. **Unreliable constraint enforcement:** It might overlook strict requirements such as maximum calories or excluded ingredients.
5. **Limited traceability:** It would be difficult to identify exactly why a particular food was recommended.

By restricting the LLM to natural-language interpretation, the project avoids making it responsible for factual nutritional decisions.

The actual recommendation is always derived from the stored knowledge base and explicit decision rules.

---

## 11. Expert System Characteristics Demonstrated by the Project

The project demonstrates several fundamental characteristics of a classical expert system.

| Characteristic | Implementation in the project |
|---|---|
| Knowledge representation | Food nutrition dataset stored in SQLite |
| Knowledge base | 597 cleaned food records and precomputed nutrient percentiles |
| Rule base | Hard filtering conditions and nutritional goal rules |
| User preference acquisition | Structured form and natural-language input |
| Inference mechanism | Rule application, filtering and preference-based scoring |
| Conflict resolution | Equal-weight percentile scoring |
| Explanation facility | Template-generated reasons and interpreted preferences |
| Knowledge acquisition | Dataset cleaning, validation and construction of nutritional attributes |
| User interface | Web-based frontend |

### Advantages of This Approach

- **Explainability:** Every recommendation can be traced to stored nutritional values and explicit rules.
- **Consistency:** The recommendation engine produces deterministic results for the same validated preferences and database state.
- **Flexibility:** Users can express their requirements through either a form or natural language.
- **Reduced hallucination:** The LLM does not generate food records or nutritional facts.
- **Graceful degradation:** The structured recommendation engine remains functional without an external LLM.
- **Maintainability:** Natural-language processing and recommendation logic are separated into independent components.

### Current Scope and Future Improvements

The current implementation uses rules defined directly in Python modules rather than a separate declarative rule base.

A future improvement would be to move the rules into an external representation such as YAML. The inference engine could then load and execute these rules independently of the application code.

Other possible improvements include:

- Adding manually verified dietary classifications such as vegetarian and non-vegetarian.
- Introducing confidence or priority weights for individual nutritional goals.
- Supporting more sophisticated keyword matching and synonyms.
- Incorporating serving-size normalization for more meaningful nutritional comparisons.
- Adding a rule-tracing mechanism to show exactly which rules fired for each recommendation.

These improvements would make the system more flexible and closer to a fully developed knowledge-based expert system.