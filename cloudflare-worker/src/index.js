import {
  ALL_FIGHT_TYPES,
  FIGHT_TYPE_LABELS,
  analyzeHeroState,
  evaluateFilters,
  normalizeRu,
} from "./boss_parser.js";
import { verifyTelegramInitData } from "./telegram_auth.js";

const VALID_MODES = ["smart", "strict", "all"];

let schemaReady = false;

async function ensureSchema(env) {
  if (schemaReady) return;
  if (!env.DB) {
    throw new Error("D1 binding env.DB is not configured");
  }
  await env.DB.batch([
    env.DB.prepare(
      `CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        god_name TEXT,
        api_token TEXT,
        base_url TEXT NOT NULL DEFAULT 'https://godville.net',
        enabled INTEGER NOT NULL DEFAULT 1,
        fight_types TEXT NOT NULL DEFAULT '["dungeon","sail"]',
        name_filters TEXT NOT NULL DEFAULT '[]',
        level_filters TEXT NOT NULL DEFAULT '[]',
        filter_mode TEXT NOT NULL DEFAULT 'smart',
        notify_unknown_entry INTEGER NOT NULL DEFAULT 0,
        last_fight_type TEXT,
        last_diary TEXT,
        last_notified_key TEXT,
        last_notified_at TEXT,
        token_warning_sent INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )`
    ),
    env.DB.prepare(
      "CREATE INDEX IF NOT EXISTS idx_users_active ON users (enabled, god_name, api_token)"
    ),
  ]);
  schemaReady = true;
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders() },
  });
}

function isAllowedTelegramId(uid, env) {
  const raw = String(env.ALLOWED_TELEGRAM_IDS || "").trim();
  if (!raw) return true;
  const set = new Set(raw.split(",").map((s) => Number(s.trim())).filter(Boolean));
  return set.has(Number(uid));
}

function rowToUser(row) {
  return {
    telegram_id: Number(row.telegram_id),
    god_name: row.god_name || null,
    api_token: row.api_token || null,
    base_url: row.base_url || "https://godville.net",
    enabled: Boolean(row.enabled),
    fight_types: JSON.parse(row.fight_types || '["dungeon","sail"]'),
    name_filters: JSON.parse(row.name_filters || "[]"),
    level_filters: JSON.parse(row.level_filters || "[]").map(Number),
    filter_mode: row.filter_mode || "smart",
    notify_unknown_entry: Boolean(row.notify_unknown_entry),
    last_fight_type: row.last_fight_type || null,
    last_diary: row.last_diary || null,
    last_notified_key: row.last_notified_key || null,
    token_warning_sent: Boolean(row.token_warning_sent),
  };
}

function serializeForWebapp(user) {
  return {
    god_name: user.god_name || "",
    has_token: Boolean(user.api_token),
    enabled: user.enabled,
    fight_types: user.fight_types,
    name_filters: user.name_filters,
    level_filters: user.level_filters,
    filter_mode: user.filter_mode,
    notify_unknown_entry: user.notify_unknown_entry,
  };
}

async function getOrCreateUser(env, telegramId) {
  await ensureSchema(env);
  let row = await env.DB.prepare("SELECT * FROM users WHERE telegram_id = ?")
    .bind(telegramId)
    .first();
  if (row) return rowToUser(row);

  const now = new Date().toISOString();
  const baseUrl = (env.GODVILLE_BASE_URL || "https://godville.net").replace(/\/+$/, "");
  await env.DB.prepare(
    `INSERT INTO users (
      telegram_id, base_url, enabled, fight_types, name_filters, level_filters,
      filter_mode, notify_unknown_entry, token_warning_sent, created_at, updated_at
    ) VALUES (?, ?, 1, '["dungeon","sail"]', '[]', '[]', 'smart', 0, 0, ?, ?)`
  )
    .bind(telegramId, baseUrl, now, now)
    .run();

  row = await env.DB.prepare("SELECT * FROM users WHERE telegram_id = ?")
    .bind(telegramId)
    .first();
  return rowToUser(row);
}

async function applySettings(env, telegramId, payload) {
  const user = await getOrCreateUser(env, telegramId);
  const fightTypes = Array.isArray(payload.fight_types)
    ? payload.fight_types.filter((x) => ALL_FIGHT_TYPES.includes(x))
    : user.fight_types;

  let nameFilters = user.name_filters;
  if (Array.isArray(payload.name_filters)) {
    const seen = new Set();
    nameFilters = [];
    for (const item of payload.name_filters) {
      const cleaned = String(item || "").trim().replace(/\s+/g, " ");
      if (cleaned && !seen.has(cleaned.toLowerCase())) {
        seen.add(cleaned.toLowerCase());
        nameFilters.push(cleaned);
      }
    }
  }

  const levelFilters = Array.isArray(payload.level_filters)
    ? Array.from(new Set(payload.level_filters.map(Number).filter((x) => x >= 1 && x <= 4))).sort()
    : user.level_filters;

  const filterMode = VALID_MODES.includes(payload.filter_mode)
    ? payload.filter_mode
    : user.filter_mode;
  const enabled = typeof payload.enabled === "boolean" ? payload.enabled : user.enabled;
  const notifyUnknown =
    typeof payload.notify_unknown_entry === "boolean"
      ? payload.notify_unknown_entry
      : user.notify_unknown_entry;

  const godName =
    typeof payload.god_name === "string" && payload.god_name.trim()
      ? payload.god_name.trim()
      : user.god_name;
  const apiToken =
    typeof payload.api_token === "string" && payload.api_token.trim()
      ? payload.api_token.trim()
      : user.api_token;

  await env.DB.prepare(
    `UPDATE users
     SET god_name = ?, api_token = ?, enabled = ?, fight_types = ?,
         name_filters = ?, level_filters = ?, filter_mode = ?,
         notify_unknown_entry = ?, updated_at = ?
     WHERE telegram_id = ?`
  )
    .bind(
      godName,
      apiToken,
      enabled ? 1 : 0,
      JSON.stringify(fightTypes),
      JSON.stringify(nameFilters),
      JSON.stringify(levelFilters),
      filterMode,
      notifyUnknown ? 1 : 0,
      new Date().toISOString(),
      telegramId
    )
    .run();

  return getOrCreateUser(env, telegramId);
}

async function fetchGodvilleHero(godName, apiToken, baseUrl = "https://godville.net") {
  const cleanBase = baseUrl.replace(/\/+$/, "");
  const encodedGod = encodeURIComponent(godName.trim());
  const url = apiToken && apiToken.trim()
    ? `${cleanBase}/gods/api/${encodedGod}/${encodeURIComponent(apiToken.trim())}`
    : `${cleanBase}/gods/api/${encodedGod}`;

  const resp = await fetch(url, {
    headers: {
      "User-Agent": "GodvilleBossTelegramBot-Worker/0.1 (+https://godville.net)",
      Accept: "application/json",
    },
  });
  if (resp.status === 404) throw new Error(`Бог '${godName}' не найден`);
  if (resp.status === 429) throw new Error("Превышен лимит запросов к API Годвилля (429)");
  if (!resp.ok) throw new Error(`HTTP ${resp.status} от Годвилля`);

  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Ответ Годвилля не JSON: ${text.slice(0, 120)}`);
  }
}

async function callTelegram(env, method, body) {
  if (!env.BOT_TOKEN) {
    throw new Error("BOT_TOKEN secret is not configured in Cloudflare Worker");
  }
  const resp = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({ ok: false, status: resp.status }));
  if (!data.ok) {
    console.error(`Telegram ${method} failed:`, JSON.stringify(data));
  }
  return data;
}

function maskToken(token) {
  if (!token) return "не задан";
  if (token.length <= 6) return "***";
  return `${token.slice(0, 3)}***${token.slice(-3)}`;
}

function formatSummary(user) {
  const statusIcon = user.enabled ? "🟢 Активен" : "⏸ На паузе";
  const god = user.god_name ? escapeHtml(user.god_name) : "<i>не привязан</i>";
  const fights = user.fight_types.map((ft) => FIGHT_TYPE_LABELS[ft] || ft).join(", ") || "<i>не выбраны</i>";
  const names = user.name_filters.length ? user.name_filters.map(escapeHtml).join(", ") : "<i>не заданы</i>";
  const levels = user.level_filters.length ? user.level_filters.map((l) => `${l} ур.`).join(", ") : "<i>не заданы</i>";
  return (
    `⚙️ <b>Настройки отслеживания</b>\n` +
    `• <b>Мониторинг:</b> ${statusIcon}\n` +
    `• <b>Бог:</b> ${god} (токен: <code>${escapeHtml(maskToken(user.api_token))}</code>)\n` +
    `• <b>Типы боёв:</b> ${fights}\n` +
    `• <b>Фильтр по имени:</b> ${names}\n` +
    `• <b>Фильтр по уровню:</b> ${levels}\n` +
    `• <b>Режим:</b> ${escapeHtml(user.filter_mode)}\n` +
    `• <b>Сигнал входа без деталей:</b> ${user.notify_unknown_entry ? "Вкл" : "Выкл"}`
  );
}

function buildKeyboard(user, webappUrl) {
  const lvlRow = [1, 2, 3, 4].map((lvl) => ({
    text: `${user.level_filters.includes(lvl) ? "✅ " : ""}${lvl} ур.`,
    callback_data: `lvl:${lvl}`,
  }));
  const ftRow1 = ALL_FIGHT_TYPES.slice(0, 2).map((ft) => ({
    text: `${user.fight_types.includes(ft) ? "✅ " : "▫️ "}${FIGHT_TYPE_LABELS[ft]}`,
    callback_data: `ft:${ft}`,
  }));
  const ftRow2 = ALL_FIGHT_TYPES.slice(2).map((ft) => ({
    text: `${user.fight_types.includes(ft) ? "✅ " : "▫️ "}${FIGHT_TYPE_LABELS[ft]}`,
    callback_data: `ft:${ft}`,
  }));
  const modeRow = [
    { text: `${user.filter_mode === "smart" ? "✅ " : ""}Умный`, callback_data: "mode:smart" },
    { text: `${user.filter_mode === "strict" ? "✅ " : ""}Строгий`, callback_data: "mode:strict" },
    { text: `${user.filter_mode === "all" ? "✅ " : ""}Все боссы`, callback_data: "mode:all" },
  ];
  const rows = [
    lvlRow,
    ftRow1,
    ftRow2,
    modeRow,
    [
      { text: user.enabled ? "⏸ Пауза" : "▶️ Включить", callback_data: "action:toggle_enabled" },
      { text: "🔄 Проверить сейчас", callback_data: "action:check_now" },
    ],
  ];
  if (webappUrl) {
    rows.push([{ text: "📱 Открыть Mini App (фильтры и каталог)", web_app: { url: webappUrl } }]);
  }
  return { inline_keyboard: rows };
}

function computeDedupKey(encounter, filterResult) {
  const fight = encounter.fightType || (encounter.arenaFight ? "arena" : "fight");
  if (filterResult?.reason === "unknown_fight_entry") return `${fight}:entry`;
  if (encounter.bossName) return `${fight}:name:${normalizeRu(encounter.bossName)}`;
  if (filterResult?.matchedNames?.length) return `${fight}:name:${normalizeRu(filterResult.matchedNames[0])}`;
  if (encounter.bossLevel !== null) return `${fight}:lvl:${encounter.bossLevel}`;
  return `${fight}:combat`;
}

function formatEncounterMessage(encounter, filterResult) {
  const isHit = filterResult.matchedNames.length > 0 || filterResult.matchedLevels.length > 0;
  const header = isHit ? "🎯 <b>Встречен нужный босс!</b>" : "⚔️ <b>Встреча с боссом!</b>";
  const fightLabel = FIGHT_TYPE_LABELS[encounter.fightType || ""] || encounter.fightType || "Бой";
  const displayName =
    encounter.bossName || (filterResult.matchedNames.length ? filterResult.matchedNames.join(", ") : null);

  const lines = [
    header,
    `• <b>Режим:</b> ${escapeHtml(fightLabel)}`,
    displayName
      ? `• <b>Босс:</b> ${escapeHtml(displayName)}`
      : "• <b>Босс:</b> <i>имя не распознано в diary_last</i>",
  ];
  if (encounter.bossLevel !== null) lines.push(`• <b>Уровень / абилки:</b> ${encounter.bossLevel}`);
  if (encounter.abilities.length) lines.push(`• <b>Способности:</b> ${encounter.abilities.map(escapeHtml).join(", ")}`);
  if (isHit) {
    const parts = [];
    if (filterResult.matchedNames.length) parts.push(`имя (${filterResult.matchedNames.map(escapeHtml).join(", ")})`);
    if (filterResult.matchedLevels.length) parts.push(`уровень (${filterResult.matchedLevels.join(", ")})`);
    lines.push(`• <b>Совпадение:</b> ${parts.join("; ")}`);
  }
  const heroBits = [escapeHtml(encounter.heroName)];
  if (encounter.heroLevel !== null) heroBits.push(`${encounter.heroLevel} ур.`);
  if (encounter.health !== null && encounter.maxHealth !== null) {
    heroBits.push(`HP ${encounter.health}/${encounter.maxHealth}`);
  }
  lines.push(`• <b>Герой:</b> ${heroBits.join(", ")}`);
  if (encounter.quest) lines.push(`• <b>Задание:</b> ${escapeHtml(encounter.quest)}`);
  if (encounter.diaryLast) lines.push(`\n📖 <i>${escapeHtml(encounter.diaryLast)}</i>`);
  return lines.join("\n");
}

async function handleTelegramUpdate(update, env, originUrl) {
  const webappUrl = (env.WEBAPP_URL || originUrl).replace(/\/+$/, "");

  if (update.callback_query) {
    const cb = update.callback_query;
    const uid = cb.from?.id;
    if (!isAllowedTelegramId(uid, env)) {
      await callTelegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "⛔ Доступ ограничен", show_alert: true });
      return;
    }
    const data = String(cb.data || "");
    let user = await getOrCreateUser(env, uid);

    if (data.startsWith("lvl:")) {
      const lvl = Number(data.split(":")[1]);
      const levels = user.level_filters.includes(lvl)
        ? user.level_filters.filter((x) => x !== lvl)
        : [...user.level_filters, lvl].sort();
      user = await applySettings(env, uid, { level_filters: levels });
    } else if (data.startsWith("ft:")) {
      const ft = data.split(":")[1];
      const fightTypes = user.fight_types.includes(ft)
        ? user.fight_types.filter((x) => x !== ft)
        : [...user.fight_types, ft];
      user = await applySettings(env, uid, { fight_types: fightTypes });
    } else if (data.startsWith("mode:")) {
      user = await applySettings(env, uid, { filter_mode: data.split(":")[1] });
    } else if (data === "action:toggle_enabled") {
      user = await applySettings(env, uid, { enabled: !user.enabled });
    } else if (data === "action:check_now") {
      await callTelegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Проверяю API..." });
      if (!user.god_name || !user.api_token) {
        await callTelegram(env, "sendMessage", {
          chat_id: uid,
          parse_mode: "HTML",
          text: "⚠️ Герой ещё не привязан. Используйте <code>/setup ИмяБога Токен</code> или Mini App.",
        });
        return;
      }
      try {
        const payload = await fetchGodvilleHero(user.god_name, user.api_token, user.base_url);
        const enc = analyzeHeroState(payload);
        await callTelegram(env, "sendMessage", {
          chat_id: uid,
          parse_mode: "HTML",
          text:
            `📊 <b>${escapeHtml(enc.heroName)}</b> (${enc.heroLevel ?? "?"} ур., HP ${enc.health ?? "?"}/${enc.maxHealth ?? "?"})\n` +
            `• Режим: ${escapeHtml(FIGHT_TYPE_LABELS[enc.fightType] || enc.fightType || "обычное приключение")}\n` +
            (enc.diaryLast ? `• Дневник: <i>${escapeHtml(enc.diaryLast)}</i>` : ""),
        });
      } catch (err) {
        await callTelegram(env, "sendMessage", {
          chat_id: uid,
          parse_mode: "HTML",
          text: `❌ Ошибка API: <code>${escapeHtml(err.message)}</code>`,
        });
      }
      return;
    }

    if (cb.message?.chat?.id && cb.message?.message_id) {
      await callTelegram(env, "editMessageText", {
        chat_id: cb.message.chat.id,
        message_id: cb.message.message_id,
        parse_mode: "HTML",
        text: formatSummary(user),
        reply_markup: buildKeyboard(user, webappUrl),
      });
    }
    await callTelegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Обновлено" });
    return;
  }

  const msg = update.message;
  if (!msg || !msg.from) return;
  const uid = msg.from.id;
  if (!isAllowedTelegramId(uid, env)) {
    await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, text: "⛔ Доступ к боту ограничен." });
    return;
  }

  if (msg.web_app_data?.data) {
    try {
      const payload = JSON.parse(msg.web_app_data.data);
      const user = await applySettings(env, uid, payload);
      await callTelegram(env, "sendMessage", {
        chat_id: msg.chat.id,
        parse_mode: "HTML",
        text: "✅ <b>Настройки из Mini App сохранены!</b>\n\n" + formatSummary(user),
        reply_markup: buildKeyboard(user, webappUrl),
      });
    } catch {
      await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, text: "❌ Ошибка чтения данных Mini App." });
    }
    return;
  }

  const text = String(msg.text || "").trim();
  if (!text.startsWith("/")) return;
  const [rawCmd, ...rest] = text.split(/\s+/);
  const cmd = rawCmd.split("@")[0].toLowerCase();
  const args = rest.join(" ").trim();
  let user = await getOrCreateUser(env, uid);

  if (cmd === "/start" || cmd === "/filters" || cmd === "/settings" || cmd === "/app") {
    await callTelegram(env, "sendMessage", {
      chat_id: msg.chat.id,
      parse_mode: "HTML",
      text:
        (cmd === "/start"
          ? "👋 <b>Бот уведомлений о боссах Годвилля (Cloudflare 24/7)</b>\n\n" +
            "Привяжите героя через <code>/setup ИмяБога Токен</code> или нажмите <b>📱 Открыть Mini App</b> ниже.\n\n"
          : "") + formatSummary(user),
      reply_markup: buildKeyboard(user, webappUrl),
    });
    return;
  }

  if (cmd === "/setup") {
    const parts = args.split(/\s+/).filter(Boolean);
    if (parts.length < 2) {
      await callTelegram(env, "sendMessage", {
        chat_id: msg.chat.id,
        parse_mode: "HTML",
        text: "Укажите имя бога и секретный API-токен:\n<code>/setup ИмяБога Ваш_API_Токен</code>",
      });
      return;
    }
    const token = parts.pop();
    const godName = parts.join(" ");
    try {
      const heroPayload = await fetchGodvilleHero(godName, token, user.base_url);
      user = await applySettings(env, uid, { god_name: godName, api_token: token });
      const enc = analyzeHeroState(heroPayload);
      await callTelegram(env, "sendMessage", {
        chat_id: msg.chat.id,
        parse_mode: "HTML",
        text:
          `✅ <b>Привязан герой:</b> ${escapeHtml(enc.heroName)}\n` +
          (enc.hasPrivateFields ? "" : "⚠️ <i>Приватные поля недоступны — проверьте API-токен!</i>\n") +
          "\n" +
          formatSummary(user),
        reply_markup: buildKeyboard(user, webappUrl),
      });
    } catch (err) {
      await callTelegram(env, "sendMessage", {
        chat_id: msg.chat.id,
        parse_mode: "HTML",
        text: `❌ Ошибка проверки API: <code>${escapeHtml(err.message)}</code>`,
      });
    }
    return;
  }

  if (cmd === "/addname") {
    if (!args) {
      await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: "Пример: <code>/addname Днищеброд, Великотушный</code>" });
      return;
    }
    const added = args.split(",").map((s) => s.trim()).filter(Boolean);
    user = await applySettings(env, uid, { name_filters: [...user.name_filters, ...added] });
    await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: formatSummary(user), reply_markup: buildKeyboard(user, webappUrl) });
    return;
  }

  if (cmd === "/delname") {
    const target = args.toLowerCase();
    user = await applySettings(env, uid, {
      name_filters: user.name_filters.filter((n) => n.toLowerCase() !== target),
    });
    await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: formatSummary(user), reply_markup: buildKeyboard(user, webappUrl) });
    return;
  }

  if (cmd === "/clearnames") {
    user = await applySettings(env, uid, { name_filters: [] });
    await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: formatSummary(user), reply_markup: buildKeyboard(user, webappUrl) });
    return;
  }

  if (cmd === "/levels") {
    const levels = args === "clear" ? [] : args.replace(/,/g, " ").split(/\s+/).map(Number).filter((n) => n >= 1 && n <= 4);
    user = await applySettings(env, uid, { level_filters: levels });
    await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: formatSummary(user), reply_markup: buildKeyboard(user, webappUrl) });
    return;
  }

  if (cmd === "/pause" || cmd === "/resume") {
    user = await applySettings(env, uid, { enabled: cmd === "/resume" });
    await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: formatSummary(user), reply_markup: buildKeyboard(user, webappUrl) });
    return;
  }

  if (cmd === "/status") {
    if (!user.god_name || !user.api_token) {
      await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: formatSummary(user), reply_markup: buildKeyboard(user, webappUrl) });
      return;
    }
    try {
      const payload = await fetchGodvilleHero(user.god_name, user.api_token, user.base_url);
      const enc = analyzeHeroState(payload);
      await callTelegram(env, "sendMessage", {
        chat_id: msg.chat.id,
        parse_mode: "HTML",
        text:
          formatSummary(user) +
          `\n\n📊 <b>${escapeHtml(enc.heroName)}</b> (${enc.heroLevel ?? "?"} ур., HP ${enc.health ?? "?"}/${enc.maxHealth ?? "?"})\n` +
          `• Режим: ${escapeHtml(FIGHT_TYPE_LABELS[enc.fightType] || enc.fightType || "обычное приключение")}\n` +
          (enc.diaryLast ? `• Дневник: <i>${escapeHtml(enc.diaryLast)}</i>` : ""),
        reply_markup: buildKeyboard(user, webappUrl),
      });
    } catch (err) {
      await callTelegram(env, "sendMessage", { chat_id: msg.chat.id, parse_mode: "HTML", text: `❌ Ошибка API: <code>${escapeHtml(err.message)}</code>` });
    }
    return;
  }

  await callTelegram(env, "sendMessage", {
    chat_id: msg.chat.id,
    parse_mode: "HTML",
    text:
      "Команды: /start, /setup, /app, /filters, /addname, /delname, /clearnames, /levels, /status, /pause, /resume",
  });
}

async function pollAllUsers(env) {
  await ensureSchema(env);
  const { results } = await env.DB.prepare(
    `SELECT * FROM users
     WHERE enabled = 1
       AND god_name IS NOT NULL AND TRIM(god_name) != ''
       AND api_token IS NOT NULL AND TRIM(api_token) != ''`
  ).all();

  for (const row of results || []) {
    const user = rowToUser(row);
    try {
      const payload = await fetchGodvilleHero(user.god_name, user.api_token, user.base_url);
      const encounter = analyzeHeroState(payload);

      if (!encounter.hasPrivateFields) {
        if (!user.token_warning_sent) {
          await callTelegram(env, "sendMessage", {
            chat_id: user.telegram_id,
            parse_mode: "HTML",
            text:
              "⚠️ <b>Приватные поля Годвилля недоступны</b> (<code>diary_last</code>, <code>fight_type</code>).\n" +
              "Проверьте API-токен через <code>/setup ИмяБога НовыйТокен</code> или в Mini App.",
          });
          await env.DB.prepare(
            "UPDATE users SET token_warning_sent = 1, last_fight_type = NULL, last_notified_key = NULL, updated_at = ? WHERE telegram_id = ?"
          )
            .bind(new Date().toISOString(), user.telegram_id)
            .run();
        }
        continue;
      }

      const isFightEntry = Boolean(encounter.fightType && encounter.fightType !== user.last_fight_type);
      const filterResult = evaluateFilters(encounter, {
        enabledFightTypes: user.fight_types,
        nameFilters: user.name_filters,
        levelFilters: user.level_filters,
        filterMode: user.filter_mode,
        notifyUnknownEntry: user.notify_unknown_entry,
        isFightEntry,
      });

      let nextNotifiedKey = user.last_notified_key;
      if (
        !encounter.isBossFight ||
        encounter.isPostFight ||
        ((encounter.fightType === "dungeon" || encounter.fightType === "sail") &&
          !encounter.isCombatSignal &&
          filterResult.matchedNames.length === 0)
      ) {
        if (
          !(
            user.notify_unknown_entry &&
            user.last_notified_key === `${encounter.fightType}:entry` &&
            encounter.fightType === user.last_fight_type
          )
        ) {
          nextNotifiedKey = null;
        }
      }

      let notifiedNow = false;
      if (filterResult.shouldNotify) {
        const dedupKey = computeDedupKey(encounter, filterResult);
        if (dedupKey !== user.last_notified_key) {
          await callTelegram(env, "sendMessage", {
            chat_id: user.telegram_id,
            parse_mode: "HTML",
            text: formatEncounterMessage(encounter, filterResult),
          });
          nextNotifiedKey = dedupKey;
          notifiedNow = true;
        }
      }

      const nextDiary = encounter.diaryLast || user.last_diary;
      const stateChanged =
        encounter.fightType !== user.last_fight_type ||
        nextDiary !== user.last_diary ||
        nextNotifiedKey !== user.last_notified_key ||
        user.token_warning_sent;

      if (stateChanged || notifiedNow) {
        const now = new Date().toISOString();
        await env.DB.prepare(
          `UPDATE users
           SET last_fight_type = ?, last_diary = ?, last_notified_key = ?,
               last_notified_at = COALESCE(?, last_notified_at),
               token_warning_sent = 0, updated_at = ?
           WHERE telegram_id = ?`
        )
          .bind(
            encounter.fightType,
            nextDiary,
            nextNotifiedKey,
            notifiedNow ? now : null,
            now,
            user.telegram_id
          )
          .run();
      }
    } catch (err) {
      console.warn(`Poll error for user ${user.telegram_id}:`, err.message);
    }
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }
    if (url.pathname === "/health") {
      let dbOk = false;
      let dbError = null;
      try {
        await ensureSchema(env);
        await env.DB.prepare("SELECT 1 AS ok").first();
        dbOk = true;
      } catch (err) {
        dbError = err.message;
      }
      return jsonResponse({
        ok: dbOk && Boolean(env.BOT_TOKEN),
        has_bot_token: Boolean(env.BOT_TOKEN),
        has_db: Boolean(env.DB),
        db_ok: dbOk,
        db_error: dbError,
      });
    }

    if (url.pathname === "/telegram/webhook" && request.method === "POST") {
      if (env.WEBHOOK_SECRET) {
        const headerSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
        if (headerSecret !== env.WEBHOOK_SECRET) {
          return new Response("Forbidden", { status: 403 });
        }
      }
      if (!env.BOT_TOKEN) {
        return jsonResponse({ ok: false, error: "BOT_TOKEN secret is not configured" }, 500);
      }
      const update = await request.json();
      try {
        await handleTelegramUpdate(update, env, url.origin);
        return jsonResponse({ ok: true });
      } catch (err) {
        console.error("Webhook error:", err);
        const chatId = update?.message?.chat?.id || update?.callback_query?.message?.chat?.id;
        if (chatId) {
          await callTelegram(env, "sendMessage", {
            chat_id: chatId,
            parse_mode: "HTML",
            text: `❌ <b>Ошибка сервера бота:</b> <code>${escapeHtml(err.message)}</code>`,
          }).catch(() => {});
        }
        return jsonResponse({ ok: false, error: err.message }, 500);
      }
    }

    if (url.pathname.startsWith("/api/")) {
      if (!env.BOT_TOKEN) {
        return jsonResponse({ error: "BOT_TOKEN не задан в настройках Worker" }, 500);
      }
      let uid;
      try {
        uid = await verifyTelegramInitData(
          request.headers.get("X-Telegram-Init-Data") || "",
          env.BOT_TOKEN
        );
      } catch (err) {
        return jsonResponse({ error: err.message }, 401);
      }
      if (!isAllowedTelegramId(uid, env)) {
        return jsonResponse({ error: "Access denied" }, 403);
      }

      if (url.pathname === "/api/state" && request.method === "GET") {
        const user = await getOrCreateUser(env, uid);
        return jsonResponse(serializeForWebapp(user));
      }

      if (url.pathname === "/api/state" && request.method === "POST") {
        const payload = await request.json().catch(() => null);
        if (!payload || typeof payload !== "object") {
          return jsonResponse({ error: "Invalid JSON" }, 400);
        }
        const user = await applySettings(env, uid, payload);
        return jsonResponse(serializeForWebapp(user));
      }

      if (url.pathname === "/api/verify" && request.method === "POST") {
        const payload = await request.json().catch(() => ({}));
        const user = await getOrCreateUser(env, uid);
        const godName = String(payload.god_name || user.god_name || "").trim();
        const apiToken = String(payload.api_token || user.api_token || "").trim();
        if (!godName || !apiToken) {
          return jsonResponse({ error: "Укажите имя бога и API-токен" }, 400);
        }
        try {
          const heroPayload = await fetchGodvilleHero(godName, apiToken, user.base_url);
          const updated = await applySettings(env, uid, { god_name: godName, api_token: apiToken });
          const enc = analyzeHeroState(heroPayload);
          return jsonResponse({
            ...serializeForWebapp(updated),
            has_private_fields: enc.hasPrivateFields,
            hero: {
              name: enc.heroName,
              level: enc.heroLevel,
              health: enc.health,
              max_health: enc.maxHealth,
              fight_type: enc.fightType,
              diary_last: enc.diaryLast,
            },
          });
        } catch (err) {
          return jsonResponse({ error: err.message }, 400);
        }
      }

      return jsonResponse({ error: "Not found" }, 404);
    }

    if (env.ASSETS) {
      return env.ASSETS.fetch(request);
    }
    return new Response("Not found", { status: 404 });
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(pollAllUsers(env));
  },
};
