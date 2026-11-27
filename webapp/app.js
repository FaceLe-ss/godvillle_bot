(function () {
  const BOSS_CATALOG = [
    // Level 1
    ["Агонщик", 1], ["Берлоггер", 1], ["Бесоподобный", 1], ["Богохулио", 1],
    ["Боссяк", 1], ["Втунец", 1], ["Дворфник", 1], ["Железопитон", 1],
    ["Жмотылёк", 1], ["Зверблюд", 1], ["Исподтишок", 1], ["Капитулист", 1],
    ["Коменданте", 1], ["Молодожор", 1], ["Мясье", 1], ["Недоеда", 1],
    ["Полнолунь", 1], ["Попрощайка", 1], ["Преподаван", 1], ["Сэроежка", 1],
    ["Танатоходец", 1], ["Утипутник", 1],
    // Level 2
    ["Болевестник", 2], ["Бушевалье", 2], ["Вчелобитник", 2], ["Дракорождённый", 2],
    ["Забивчивый", 2], ["Заплутон", 2], ["Кротограф", 2], ["Крутюрье", 2],
    ["Надиратель", 2], ["Ничегоблин", 2], ["Обомлев", 2], ["Остепенитель", 2],
    ["Пожорник", 2], ["Примятель", 2], ["Сатаняшка", 2], ["Страшник", 2],
    ["Телоранитель", 2], ["Харчеватель", 2], ["Черепакостник", 2], ["Швейцарь", 2],
    // Level 3
    ["Администраж", 3], ["Амбаловень", 3], ["Бешенец", 3], ["Бомбуин", 3],
    ["Босспитатель", 3], ["Бревень", 3], ["Бревнолицый", 3], ["Великотушный", 3],
    ["Всёгун", 3], ["Втиран", 3], ["Гарантюа", 3], ["Гаубийца", 3],
    ["Генеракл", 3], ["Глыберал", 3], ["Днищеброд", 3], ["Люцемер", 3],
    ["Монстрейшина", 3], ["Нехилер", 3], ["Отъелло", 3], ["Разворотила", 3],
    ["Скушатель", 3], ["Танкистадор", 3], ["Укрупье", 3], ["Фингалист", 3],
    // Level 4
    ["Глодочник", 4], ["Данжеватель", 4], ["Дровецкий", 4], ["Дюжегуб", 4],
    ["Лжинн", 4], ["Лихорадий", 4], ["Ломамонт", 4], ["Мохнарх", 4],
    ["Необходимый", 4], ["Необык", 4], ["Пресекач", 4], ["Прессонаж", 4],
    ["Проорк", 4], ["Ротозевс", 4], ["Спилист", 4], ["Ссылач", 4],
    ["Терзан", 4], ["Упекун", 4], ["Экзекудза", 4], ["Ямбал", 4]
  ];

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const params = new URLSearchParams(window.location.search);
  const explicitApi = params.get("api");
  const encodedState = params.get("state");
  const isGithubPages = window.location.hostname.endsWith("github.io");
  const isLocalFile = window.location.protocol === "file:";

  const transport = {
    mode: "preview", // "api" | "sendData" | "preview"
    apiBase: ""
  };

  if (explicitApi) {
    transport.mode = "api";
    transport.apiBase = explicitApi.replace(/\/+$/, "");
  } else if (encodedState) {
    transport.mode = "sendData";
  } else if (tg && tg.initData && !isGithubPages && !isLocalFile) {
    transport.mode = "api";
    transport.apiBase = "";
  } else if (tg) {
    transport.mode = "sendData";
  }

  const state = {
    god_name: "",
    has_token: false,
    enabled: true,
    fight_types: ["dungeon", "sail"],
    name_filters: [],
    level_filters: [],
    filter_mode: "smart",
    notify_unknown_entry: false,
    catalog_level: "all",
    catalog_query: ""
  };

  const els = {
    statusBadge: document.getElementById("statusBadge"),
    previewBanner: document.getElementById("previewBanner"),
    apiModeTag: document.getElementById("apiModeTag"),
    apiCredentialsForm: document.getElementById("apiCredentialsForm"),
    sendDataCredsNote: document.getElementById("sendDataCredsNote"),
    sendDataGodName: document.getElementById("sendDataGodName"),
    godNameInput: document.getElementById("godNameInput"),
    apiTokenInput: document.getElementById("apiTokenInput"),
    checkHeroBtn: document.getElementById("checkHeroBtn"),
    heroLiveCard: document.getElementById("heroLiveCard"),
    levelsGrid: document.getElementById("levelsGrid"),
    clearLevelsBtn: document.getElementById("clearLevelsBtn"),
    bossNameInput: document.getElementById("bossNameInput"),
    addNameBtn: document.getElementById("addNameBtn"),
    clearNamesBtn: document.getElementById("clearNamesBtn"),
    selectedNamesChips: document.getElementById("selectedNamesChips"),
    catalogSearchInput: document.getElementById("catalogSearchInput"),
    catalogLevelTabs: document.getElementById("catalogLevelTabs"),
    catalogGrid: document.getElementById("catalogGrid"),
    fightTypesGrid: document.getElementById("fightTypesGrid"),
    filterModeGroup: document.getElementById("filterModeGroup"),
    enabledToggle: document.getElementById("enabledToggle"),
    unknownEntryToggle: document.getElementById("unknownEntryToggle"),
    saveBtn: document.getElementById("saveBtn"),
    toast: document.getElementById("toast")
  };

  let toastTimer = null;
  function showToast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.add("hidden"), 2600);
  }

  function haptic() {
    try {
      tg?.HapticFeedback?.impactOccurred("light");
    } catch (_) {}
  }

  function decodeStateParam(raw) {
    if (!raw) return null;
    try {
      const b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
      const pad = b64.length % 4 === 0 ? "" : "=".repeat(4 - (b64.length % 4));
      const binary = atob(b64 + pad);
      const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      const jsonStr = new TextDecoder().decode(bytes);
      return JSON.parse(jsonStr);
    } catch (_) {
      return null;
    }
  }

  function applyLoadedState(loaded) {
    if (!loaded || typeof loaded !== "object") return;
    if (typeof loaded.god_name === "string") state.god_name = loaded.god_name;
    if (typeof loaded.has_token === "boolean") state.has_token = loaded.has_token;
    if (typeof loaded.enabled === "boolean") state.enabled = loaded.enabled;
    if (Array.isArray(loaded.fight_types)) state.fight_types = loaded.fight_types.slice();
    if (Array.isArray(loaded.name_filters)) state.name_filters = loaded.name_filters.slice();
    if (Array.isArray(loaded.level_filters)) {
      state.level_filters = loaded.level_filters.map(Number).filter((x) => x >= 1 && x <= 4);
    }
    if (["smart", "strict", "all"].includes(loaded.filter_mode)) {
      state.filter_mode = loaded.filter_mode;
    }
    if (typeof loaded.notify_unknown_entry === "boolean") {
      state.notify_unknown_entry = loaded.notify_unknown_entry;
    }
  }

  function render() {
    els.statusBadge.textContent = state.enabled ? "Активен" : "На паузе";
    els.statusBadge.className = "badge " + (state.enabled ? "badge-active" : "badge-paused");

    if (transport.mode === "api") {
      els.apiModeTag.textContent = "Live API";
      els.apiCredentialsForm.classList.remove("hidden");
      els.sendDataCredsNote.classList.add("hidden");
      els.godNameInput.value = state.god_name || "";
      els.apiTokenInput.placeholder = state.has_token
        ? "Токен сохранён (введите новый, если нужно сменить)"
        : "Скопируйте токен из профиля godville.net";
    } else if (transport.mode === "sendData") {
      els.apiModeTag.textContent = "Telegram Sync";
      els.apiCredentialsForm.classList.add("hidden");
      els.sendDataCredsNote.classList.remove("hidden");
      els.sendDataGodName.textContent = state.god_name || "не привязан";
    } else {
      els.apiModeTag.textContent = "Preview";
      els.apiCredentialsForm.classList.remove("hidden");
      els.sendDataCredsNote.classList.add("hidden");
      els.previewBanner.textContent =
        "Открыто вне Telegram (режим предпросмотра). Запустите Mini App через кнопку в боте для сохранения.";
      els.previewBanner.classList.remove("hidden");
    }

    // Levels
    els.levelsGrid.querySelectorAll(".level-card").forEach((btn) => {
      const lvl = Number(btn.dataset.level);
      btn.classList.toggle("selected", state.level_filters.includes(lvl));
    });

    // Selected name chips
    els.selectedNamesChips.innerHTML = "";
    if (state.name_filters.length === 0) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "Имена не выбраны (подходят любые при пустых фильтрах или совпадении по уровню).";
      els.selectedNamesChips.appendChild(empty);
    } else {
      state.name_filters.forEach((name) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        const label = document.createElement("span");
        label.textContent = name;
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.textContent = "×";
        removeBtn.title = "Удалить";
        removeBtn.addEventListener("click", () => {
          haptic();
          state.name_filters = state.name_filters.filter(
            (n) => n.toLowerCase() !== name.toLowerCase()
          );
          render();
        });
        chip.append(label, removeBtn);
        els.selectedNamesChips.appendChild(chip);
      });
    }

    // Catalog grid
    const activeLower = new Set(state.name_filters.map((n) => n.toLowerCase()));
    const q = state.catalog_query.trim().toLowerCase().replace(/ё/g, "е");
    els.catalogGrid.innerHTML = "";
    BOSS_CATALOG.filter(([name, lvl]) => {
      if (state.catalog_level !== "all" && lvl !== Number(state.catalog_level)) return false;
      if (q && !name.toLowerCase().replace(/ё/g, "е").includes(q)) return false;
      return true;
    }).forEach(([name, lvl]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const isSelected = activeLower.has(name.toLowerCase());
      btn.className = "cat-boss" + (isSelected ? " selected" : "");
      const nameSpan = document.createElement("span");
      nameSpan.textContent = name;
      const lvlSpan = document.createElement("span");
      lvlSpan.className = "cat-lvl";
      lvlSpan.textContent = `${lvl}у`;
      btn.append(nameSpan, lvlSpan);
      btn.addEventListener("click", () => {
        haptic();
        if (isSelected) {
          state.name_filters = state.name_filters.filter(
            (n) => n.toLowerCase() !== name.toLowerCase()
          );
        } else {
          state.name_filters.push(name);
        }
        render();
      });
      els.catalogGrid.appendChild(btn);
    });

    // Fight types
    els.fightTypesGrid.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.checked = state.fight_types.includes(cb.value);
    });

    // Filter mode
    els.filterModeGroup.querySelectorAll('input[type="radio"]').forEach((rb) => {
      rb.checked = rb.value === state.filter_mode;
    });

    els.enabledToggle.checked = state.enabled;
    els.unknownEntryToggle.checked = state.notify_unknown_entry;
  }

  function addNamesFromInput() {
    const raw = els.bossNameInput.value.trim();
    if (!raw) return;
    const existingLower = new Set(state.name_filters.map((n) => n.toLowerCase()));
    raw.split(",").forEach((part) => {
      const cleaned = part.trim().replace(/\s+/g, " ");
      if (cleaned && !existingLower.has(cleaned.toLowerCase())) {
        state.name_filters.push(cleaned);
        existingLower.add(cleaned.toLowerCase());
      }
    });
    els.bossNameInput.value = "";
    haptic();
    render();
  }

  // Event listeners
  els.levelsGrid.querySelectorAll(".level-card").forEach((btn) => {
    btn.addEventListener("click", () => {
      haptic();
      const lvl = Number(btn.dataset.level);
      if (state.level_filters.includes(lvl)) {
        state.level_filters = state.level_filters.filter((x) => x !== lvl);
      } else {
        state.level_filters = [...state.level_filters, lvl].sort();
      }
      render();
    });
  });

  els.clearLevelsBtn.addEventListener("click", () => {
    haptic();
    state.level_filters = [];
    render();
  });

  els.addNameBtn.addEventListener("click", addNamesFromInput);
  els.bossNameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addNamesFromInput();
    }
  });

  els.clearNamesBtn.addEventListener("click", () => {
    haptic();
    state.name_filters = [];
    render();
  });

  els.catalogSearchInput.addEventListener("input", () => {
    state.catalog_query = els.catalogSearchInput.value;
    render();
  });

  els.catalogLevelTabs.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      els.catalogLevelTabs.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.catalog_level = btn.dataset.catLvl || "all";
      render();
    });
  });

  els.fightTypesGrid.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", () => {
      haptic();
      const selected = [];
      els.fightTypesGrid.querySelectorAll('input[type="checkbox"]').forEach((x) => {
        if (x.checked) selected.push(x.value);
      });
      state.fight_types = selected;
    });
  });

  els.filterModeGroup.querySelectorAll('input[type="radio"]').forEach((rb) => {
    rb.addEventListener("change", () => {
      haptic();
      if (rb.checked) state.filter_mode = rb.value;
    });
  });

  els.enabledToggle.addEventListener("change", () => {
    haptic();
    state.enabled = els.enabledToggle.checked;
    render();
  });

  els.unknownEntryToggle.addEventListener("change", () => {
    haptic();
    state.notify_unknown_entry = els.unknownEntryToggle.checked;
  });

  async function apiRequest(path, options = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      options.headers || {}
    );
    if (tg && tg.initData) {
      headers["X-Telegram-Init-Data"] = tg.initData;
    }
    const resp = await fetch(`${transport.apiBase}${path}`, {
      ...options,
      headers
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    return data;
  }

  async function checkAndSaveCredentials() {
    if (transport.mode !== "api") {
      showToast("В статическом режиме используйте /setup в чате с ботом");
      return;
    }
    const godName = els.godNameInput.value.trim();
    const apiToken = els.apiTokenInput.value.trim();
    if (!godName) {
      showToast("Введите имя бога");
      return;
    }
    els.checkHeroBtn.disabled = true;
    els.checkHeroBtn.textContent = "Проверяю...";
    try {
      const result = await apiRequest("/api/verify", {
        method: "POST",
        body: JSON.stringify({ god_name: godName, api_token: apiToken || undefined })
      });
      state.god_name = result.god_name || godName;
      state.has_token = Boolean(result.has_token);
      els.apiTokenInput.value = "";
      els.heroLiveCard.classList.remove("hidden");
      els.heroLiveCard.innerHTML = "";
      const hero = result.hero || {};
      const fight = hero.fight_type || "обычное приключение";
      const priv = result.has_private_fields
        ? "Приватные поля доступны"
        : "Внимание: приватные поля не получены — проверьте API-токен";

      const p1 = document.createElement("p");
      const strong = document.createElement("strong");
      strong.textContent = hero.name || "Герой";
      p1.append(
        strong,
        document.createTextNode(
          ` (${hero.level || "?"} ур., HP ${hero.health ?? "?"}/${hero.max_health ?? "?"})`
        )
      );
      const p2 = document.createElement("p");
      p2.className = "muted";
      p2.textContent = `Режим: ${fight} · ${priv}`;
      els.heroLiveCard.append(p1, p2);
      if (hero.diary_last) {
        const p3 = document.createElement("p");
        const em = document.createElement("em");
        em.textContent = hero.diary_last;
        p3.appendChild(em);
        els.heroLiveCard.appendChild(p3);
      }
      showToast("Герой проверен и сохранён");
      render();
    } catch (err) {
      showToast(`Ошибка: ${err.message}`);
    } finally {
      els.checkHeroBtn.disabled = false;
      els.checkHeroBtn.textContent = "Проверить и привязать";
    }
  }

  els.checkHeroBtn.addEventListener("click", checkAndSaveCredentials);

  async function saveAllSettings() {
    const payload = {
      enabled: state.enabled,
      fight_types: state.fight_types,
      name_filters: state.name_filters,
      level_filters: state.level_filters,
      filter_mode: state.filter_mode,
      notify_unknown_entry: state.notify_unknown_entry
    };

    if (transport.mode === "api") {
      els.saveBtn.disabled = true;
      els.saveBtn.textContent = "Сохраняю...";
      try {
        if (els.godNameInput.value.trim()) {
          payload.god_name = els.godNameInput.value.trim();
        }
        if (els.apiTokenInput.value.trim()) {
          payload.api_token = els.apiTokenInput.value.trim();
        }
        const saved = await apiRequest("/api/state", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        applyLoadedState(saved);
        els.apiTokenInput.value = "";
        render();
        showToast("Настройки сохранены!");
      } catch (err) {
        showToast(`Ошибка сохранения: ${err.message}`);
      } finally {
        els.saveBtn.disabled = false;
        els.saveBtn.textContent = "Сохранить настройки";
      }
      return;
    }

    if (transport.mode === "sendData" && tg) {
      try {
        tg.sendData(JSON.stringify(payload));
        showToast("Отправлено в Telegram-бота");
      } catch (err) {
        showToast("Откройте Mini App через кнопку под полем ввода в боте");
      }
      return;
    }

    localStorage.setItem("godville_boss_preview_state", JSON.stringify(payload));
    showToast("Сохранено в локальный предпросмотр браузера");
  }

  els.saveBtn.addEventListener("click", saveAllSettings);

  const inTelegram = Boolean(
    tg && (tg.initData || (tg.platform && tg.platform !== "unknown"))
  );

  if (inTelegram && tg && tg.MainButton) {
    document.body.classList.add("in-telegram");
    tg.MainButton.setText("Сохранить настройки");
    tg.MainButton.show();
    tg.MainButton.onClick(saveAllSettings);
  }

  async function init() {
    if (encodedState) {
      applyLoadedState(decodeStateParam(encodedState));
    } else if (transport.mode === "preview") {
      try {
        const cached = localStorage.getItem("godville_boss_preview_state");
        if (cached) applyLoadedState(JSON.parse(cached));
      } catch (_) {}
    }

    if (transport.mode === "api") {
      try {
        const remoteState = await apiRequest("/api/state");
        applyLoadedState(remoteState);
      } catch (err) {
        if (!explicitApi && tg && String(err.message || "").includes("404")) {
          // Fallback to sendData mode only when backend /api/state endpoint does not exist (static GitHub Pages).
          transport.mode = "sendData";
        } else {
          els.previewBanner.textContent = `Ошибка API: ${err.message}`;
          els.previewBanner.classList.remove("hidden");
          showToast(`Ошибка загрузки настроек: ${err.message}`);
        }
      }
    }

    render();
  }

  init();
})();
