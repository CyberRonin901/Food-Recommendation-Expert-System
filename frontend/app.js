document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const recommenderForm = document.getElementById("recommenderForm");
  const queryInput = document.getElementById("queryInput");
  const mealTypeSelect = document.getElementById("mealTypeSelect");
  const goalsContainer = document.getElementById("goalsContainer");
  const categoriesContainer = document.getElementById("categoriesContainer");
  const includeKeywordsInput = document.getElementById("includeKeywords");
  const excludeKeywordsInput = document.getElementById("excludeKeywords");
  const includeCondimentsCheckbox = document.getElementById("includeCondiments");
  const topKInput = document.getElementById("topKInput");
  const submitBtn = document.getElementById("submitBtn");
  const resetBtn = document.getElementById("resetBtn");
  const btnText = submitBtn.querySelector(".btn-text");
  const spinner = submitBtn.querySelector(".spinner");

  // Status & Banners
  const systemStatus = document.getElementById("systemStatus");
  const statusText = document.getElementById("statusText");
  const llmIndicator = document.getElementById("llmIndicator");
  const errorBanner = document.getElementById("errorBanner");
  const warningsBanner = document.getElementById("warningsBanner");
  const interpretedBanner = document.getElementById("interpretedBanner");
  const interpretedContent = document.getElementById("interpretedContent");
  const resultsHeader = document.getElementById("resultsHeader");
  const matchesCountTitle = document.getElementById("matchesCountTitle");
  const matchesSubtitle = document.getElementById("matchesSubtitle");
  const resultsGrid = document.getElementById("resultsGrid");

  // Nutrient inputs
  const nutrientInputs = {
    min_calories: document.getElementById("minCalories"),
    max_calories: document.getElementById("maxCalories"),
    min_protein: document.getElementById("minProtein"),
    max_carbs: document.getElementById("maxCarbs"),
    max_fat: document.getElementById("maxFat"),
    min_fiber: document.getElementById("minFiber"),
    max_sugars: document.getElementById("maxSugars"),
    max_sodium: document.getElementById("maxSodium"),
    max_cholesterol: document.getElementById("maxCholesterol"),
  };

  // 1. Fetch Health Status
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Health check failed");
      const data = await res.json();
      const dot = systemStatus.querySelector(".status-dot");
      dot.classList.add("active");
      statusText.textContent = `${data.foods} Foods Indexed`;

      if (data.llm_configured) {
        const providerName = data.llm_provider === "ollama" ? `Ollama: ${data.llm_model}` : `API: ${data.llm_model}`;
        llmIndicator.textContent = `${providerName}`;
        llmIndicator.style.background = "#eff6ff";
        llmIndicator.style.color = "#2563eb";
      } else {
        llmIndicator.textContent = "AI Key Missing (Form Only)";
        llmIndicator.style.background = "#f1f5f9";
        llmIndicator.style.color = "#64748b";
      }
    } catch (err) {
      statusText.textContent = "Offline";
      console.error(err);
    }
  }

  // 2. Fetch Options
  async function loadOptions() {
    try {
      const res = await fetch("/api/options");
      if (!res.ok) throw new Error("Failed to load options");
      const data = await res.json();

      // Meal types
      mealTypeSelect.innerHTML = '<option value="">Any Meal Type</option>';
      data.meal_types.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        mealTypeSelect.appendChild(opt);
      });

      // Goals
      goalsContainer.innerHTML = "";
      data.goals.forEach((g) => {
        const label = document.createElement("label");
        label.className = "chip-checkbox";
        label.innerHTML = `
          <input type="checkbox" name="goals" value="${g.id}">
          <span>${g.label}</span>
        `;
        label.querySelector("input").addEventListener("change", (e) => {
          label.classList.toggle("active", e.target.checked);
        });
        goalsContainer.appendChild(label);
      });

      // Categories
      categoriesContainer.innerHTML = "";
      data.categories.forEach((cat) => {
        const label = document.createElement("label");
        label.className = "chip-checkbox";
        label.innerHTML = `
          <input type="checkbox" name="categories" value="${cat}">
          <span>${cat}</span>
        `;
        label.querySelector("input").addEventListener("change", (e) => {
          label.classList.toggle("active", e.target.checked);
        });
        categoriesContainer.appendChild(label);
      });

      // Nutrient limits placeholders
      if (data.nutrient_ranges) {
        const nr = data.nutrient_ranges;
        if (nr.calories) {
          nutrientInputs.min_calories.placeholder = `min ${nr.calories.min}`;
          nutrientInputs.max_calories.placeholder = `max ${nr.calories.max}`;
        }
        if (nr.protein_g) {
          nutrientInputs.min_protein.placeholder = `min ${nr.protein_g.min}`;
        }
        if (nr.carbs_g) {
          nutrientInputs.max_carbs.placeholder = `max ${nr.carbs_g.max}`;
        }
        if (nr.fat_g) {
          nutrientInputs.max_fat.placeholder = `max ${nr.fat_g.max}`;
        }
        if (nr.fiber_g) {
          nutrientInputs.min_fiber.placeholder = `min ${nr.fiber_g.min}`;
        }
        if (nr.sugars_g) {
          nutrientInputs.max_sugars.placeholder = `max ${nr.sugars_g.max}`;
        }
        if (nr.sodium_mg) {
          nutrientInputs.max_sodium.placeholder = `max ${nr.sodium_mg.max}`;
        }
        if (nr.cholesterol_mg) {
          nutrientInputs.max_cholesterol.placeholder = `max ${nr.cholesterol_mg.max}`;
        }
      }
    } catch (err) {
      console.error("Error loading options:", err);
      showError("Failed to load options from backend API.");
    }
  }

  // 3. Query Example Buttons
  document.querySelectorAll(".btn-chip[data-query]").forEach((btn) => {
    btn.addEventListener("click", () => {
      queryInput.value = btn.getAttribute("data-query");
      recommenderForm.dispatchEvent(new Event("submit"));
    });
  });

  // 4. Form Submit
  recommenderForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearMessages();
    setLoading(true);

    const body = buildPayload();

    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        let errData;
        try {
          errData = await res.json();
        } catch {
          errData = { detail: res.statusText };
        }
        if (res.status === 422 && Array.isArray(errData.detail)) {
          const msg = errData.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
          showError(`Validation Error: ${msg}`);
        } else {
          showError(errData.detail || "An error occurred while finding recommendations.");
        }
        setLoading(false);
        return;
      }

      const data = await res.json();
      renderResponse(data);
    } catch (err) {
      console.error(err);
      showError("Could not reach backend server. Please verify the application is running.");
    } finally {
      setLoading(false);
    }
  });

  // 5. Reset Form
  resetBtn.addEventListener("click", () => {
    recommenderForm.reset();
    document.querySelectorAll(".chip-checkbox").forEach((cb) => cb.classList.remove("active"));
    clearMessages();
    resultsHeader.style.display = "none";
    resultsGrid.innerHTML = `
      <div class="empty-placeholder">
        <div class="empty-icon">🍽️</div>
        <h3>Ready to find food recommendations</h3>
        <p>Select your preferences or enter a description above, then click <strong>Find Foods</strong>.</p>
      </div>
    `;
  });

  function buildPayload() {
    const payload = {};

    const query = queryInput.value.trim();
    if (query) payload.query = query;

    const mealType = mealTypeSelect.value;
    if (mealType) payload.meal_type = mealType;

    const selectedCategories = Array.from(
      categoriesContainer.querySelectorAll("input[type='checkbox']:checked")
    ).map((cb) => cb.value);
    if (selectedCategories.length > 0) payload.categories = selectedCategories;

    const selectedGoals = Array.from(
      goalsContainer.querySelectorAll("input[type='checkbox']:checked")
    ).map((cb) => cb.value);
    if (selectedGoals.length > 0) payload.goals = selectedGoals;

    // Nutrient limits
    for (const [key, el] of Object.entries(nutrientInputs)) {
      if (el.value !== "" && !isNaN(parseFloat(el.value))) {
        payload[key] = parseFloat(el.value);
      }
    }

    // Include / Exclude keywords
    const incWords = includeKeywordsInput.value
      .split(",")
      .map((w) => w.trim())
      .filter(Boolean);
    if (incWords.length > 0) payload.include_keywords = incWords;

    const excWords = excludeKeywordsInput.value
      .split(",")
      .map((w) => w.trim())
      .filter(Boolean);
    if (excWords.length > 0) payload.exclude_keywords = excWords;

    if (includeCondimentsCheckbox.checked) {
      payload.include_condiments = true;
    }

    const topK = parseInt(topKInput.value, 10);
    if (!isNaN(topK) && topK > 0) {
      payload.top_k = topK;
    }

    return payload;
  }

  function renderResponse(data) {
    // Warnings
    if (data.warnings && data.warnings.length > 0) {
      warningsBanner.innerHTML = data.warnings
        .map((w) => `<div>⚠️ ${escapeHtml(w)}</div>`)
        .join("");
      warningsBanner.style.display = "block";
    }

    // Interpreted Preferences
    if (data.interpreted && Object.keys(data.interpreted).length > 0) {
      interpretedContent.innerHTML = "";
      for (const [k, v] of Object.entries(data.interpreted)) {
        const pill = document.createElement("span");
        pill.className = "interpreted-pill";
        const valStr = Array.isArray(v) ? v.join(", ") : String(v);
        pill.textContent = `${formatKey(k)}: ${valStr}`;
        interpretedContent.appendChild(pill);
      }
      interpretedBanner.style.display = "block";
    }

    // Results Header
    resultsHeader.style.display = "flex";
    matchesCountTitle.textContent = `${data.total_matches} Match${data.total_matches === 1 ? "" : "es"} Found`;
    matchesSubtitle.textContent = `Showing top ${data.results.length} food recommendations`;

    // Results Cards
    if (data.results.length === 0) {
      resultsGrid.innerHTML = `
        <div class="empty-placeholder">
          <div class="empty-icon">🔍</div>
          <h3>No matching foods found</h3>
          <p>Try broadening your search or relaxing nutrient limits.</p>
        </div>
      `;
      return;
    }

    resultsGrid.innerHTML = "";
    data.results.forEach((food) => {
      const card = document.createElement("div");
      card.className = "food-card";

      const scoreHtml =
        food.score !== null && food.score !== undefined
          ? `<div class="score-badge"><span class="score-val">${food.score}</span><span class="score-label">Match Score</span></div>`
          : `<div class="score-badge" style="background:#f1f5f9; color:#475569; border-color:#cbd5e1;"><span class="score-val">-</span><span class="score-label">Alphabetical</span></div>`;

      const reasonsHtml =
        food.reasons && food.reasons.length > 0
          ? `<ul class="reasons-list">
              ${food.reasons
                .map(
                  (r) =>
                    `<li class="reason-item"><span class="reason-icon">✓</span> <span>${escapeHtml(
                      r
                    )}</span></li>`
                )
                .join("")}
            </ul>`
          : "";

      card.innerHTML = `
        <div class="card-top">
          <div>
            <h3 class="food-name-title">${escapeHtml(food.name)}</h3>
            <div class="food-meta">
              <span class="meta-tag">🍽️ ${escapeHtml(food.meal_type)}</span>
              <span class="meta-tag">🏷️ ${escapeHtml(food.category)}</span>
            </div>
          </div>
          ${scoreHtml}
        </div>

        <div class="nutrients-table">
          <div class="nut-cell"><span class="nut-name">Calories</span><span class="nut-val">${food.calories} kcal</span></div>
          <div class="nut-cell"><span class="nut-name">Protein</span><span class="nut-val">${food.protein_g} g</span></div>
          <div class="nut-cell"><span class="nut-name">Carbs</span><span class="nut-val">${food.carbs_g} g</span></div>
          <div class="nut-cell"><span class="nut-name">Fat</span><span class="nut-val">${food.fat_g} g</span></div>
          <div class="nut-cell"><span class="nut-name">Fiber</span><span class="nut-val">${food.fiber_g} g</span></div>
          <div class="nut-cell"><span class="nut-name">Sugars</span><span class="nut-val">${food.sugars_g} g</span></div>
          <div class="nut-cell"><span class="nut-name">Sodium</span><span class="nut-val">${food.sodium_mg} mg</span></div>
          <div class="nut-cell"><span class="nut-name">Cholesterol</span><span class="nut-val">${food.cholesterol_mg} mg</span></div>
        </div>

        ${reasonsHtml}
      `;
      resultsGrid.appendChild(card);
    });
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    if (loading) {
      btnText.textContent = "Finding Foods...";
      spinner.style.display = "inline-block";
    } else {
      btnText.textContent = "Find Foods";
      spinner.style.display = "none";
    }
  }

  function clearMessages() {
    errorBanner.style.display = "none";
    errorBanner.textContent = "";
    warningsBanner.style.display = "none";
    warningsBanner.innerHTML = "";
    interpretedBanner.style.display = "none";
    interpretedContent.innerHTML = "";
  }

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.style.display = "block";
  }

  function formatKey(key) {
    return key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial startup
  checkHealth();
  loadOptions();
});

