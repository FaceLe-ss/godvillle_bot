export const ALL_FIGHT_TYPES = ["dungeon", "sail", "boss", "boss_m"];

export const FIGHT_TYPE_LABELS = {
  dungeon: "Подземелье",
  sail: "Море (заплыв)",
  boss: "Босс мини-квеста",
  boss_m: "Наземный босс (зацеп)",
};

export const KNOWN_BOSS_LEVELS = {
  // Level 1
  Агонщик: 1, Берлоггер: 1, Бесоподобный: 1, Богохулио: 1, Боссяк: 1, Втунец: 1,
  Дворфник: 1, Железопитон: 1, Жмотылёк: 1, Зверблюд: 1, Исподтишок: 1, Капитулист: 1,
  Коменданте: 1, Молодожор: 1, Мясье: 1, Недоеда: 1, Полнолунь: 1, Попрощайка: 1,
  Преподаван: 1, Сэроежка: 1, Танатоходец: 1, Утипутник: 1,
  // Level 2
  Болевестник: 2, Бушевалье: 2, Вчелобитник: 2, Дракорождённый: 2, Забивчивый: 2,
  Заплутон: 2, Кротограф: 2, Крутюрье: 2, Надиратель: 2, Ничегоблин: 2, Обомлев: 2,
  Остепенитель: 2, Пожорник: 2, Примятель: 2, Сатаняшка: 2, Страшник: 2,
  Телоранитель: 2, Харчеватель: 2, Черепакостник: 2, Швейцарь: 2,
  // Level 3
  Администраж: 3, Бомбуин: 3, Великотушный: 3, Всёгун: 3, Гарантюа: 3, Генеракл: 3,
  Днищеброд: 3, Монстрейшина: 3, Укрупье: 3,
  // Level 4
  Глодочник: 4, Данжеватель: 4, Дровецкий: 4, Дюжегуб: 4, Лжинн: 4, Лихорадий: 4,
  Ломамонт: 4, Мохнарх: 4, Необходимый: 4, Необык: 4, Пресекач: 4, Прессонаж: 4,
  Проорк: 4, Ротозевс: 4, Спилист: 4, Ссылач: 4, Терзан: 4, Упекун: 4,
};

const BOSS_ABILITY_PREFIXES = [
  ["бойк", "Бойкий"],
  ["взрывн", "Взрывной"],
  ["глушащ", "Глушащий"],
  ["драпающ", "Драпающий"],
  ["золотоносн", "Золотоносный"],
  ["зовущ", "Зовущий"],
  ["крепчающ", "Крепчающий"],
  ["лучезарн", "Лучезарный"],
  ["ломающ", "Ломающий"],
  ["мощн", "Мощный"],
  ["мним", "Мнимый"],
  ["неверующ", "Неверующий"],
  ["паразитирующ", "Паразитирующий"],
  ["пробивающ", "Пробивающий"],
  ["спешащ", "Спешащий"],
  ["тащущ", "Тащущий"],
  ["тащащ", "Тащащий"],
  ["творящ", "Творящий"],
  ["транжирящ", "Транжирящий"],
];

const RU_ENDINGS = [
  "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "ью",
  "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ую", "юю",
  "ом", "ем", "им", "ым", "ах", "ях", "ов", "ев", "ам", "ям",
  "а", "я", "у", "ю", "е", "и", "ы", "о", "ь",
];

const CATALOG_BY_NORM = Object.entries(KNOWN_BOSS_LEVELS).map(([name, level]) => ({
  norm: normalizeRu(name),
  name,
  level,
}));

export function normalizeRu(text) {
  return String(text || "").toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
}

export function tokenizeRu(text) {
  return normalizeRu(text).match(/[a-zа-я0-9-]+/gi) || [];
}

export function russianStem(word) {
  const norm = normalizeRu(word);
  if (norm.length <= 4) return norm;
  for (const ending of RU_ENDINGS) {
    if (norm.endsWith(ending) && norm.length - ending.length >= 4) {
      return norm.slice(0, -ending.length);
    }
  }
  return norm;
}

function tokensMatch(filterToken, textToken) {
  if (filterToken === textToken) return true;
  const fStem = russianStem(filterToken);
  const tStem = russianStem(textToken);
  if (fStem.length >= 4 && fStem === tStem) return true;
  if (filterToken.length >= 5 && textToken.startsWith(fStem) && fStem.length >= 4) return true;
  return false;
}

export function matchesBossName(nameFilter, ...texts) {
  const filterTokens = tokenizeRu(nameFilter);
  if (!filterTokens.length) return false;
  for (const text of texts) {
    if (!text) continue;
    const textTokens = tokenizeRu(text);
    if (!textTokens.length) continue;
    if (filterTokens.length === 1) {
      if (textTokens.some((tt) => tokensMatch(filterTokens[0], tt))) return true;
    } else {
      const n = filterTokens.length;
      for (let i = 0; i <= textTokens.length - n; i += 1) {
        const win = textTokens.slice(i, i + n);
        if (filterTokens.every((ft, idx) => tokensMatch(ft, win[idx]))) return true;
      }
    }
  }
  return false;
}

export function detectCatalogBoss(text) {
  const tokens = tokenizeRu(text);
  for (const entry of CATALOG_BY_NORM) {
    if (tokens.some((tok) => tokensMatch(entry.norm, tok))) return entry;
  }
  return null;
}

export function detectAbilities(text) {
  const norm = normalizeRu(text);
  const stems = BOSS_ABILITY_PREFIXES.map(([s]) => s).join("|");
  const re = new RegExp(`(^|[^a-zа-я0-9-])(${stems})[а-я]{1,4}(?=$|[^a-zа-я0-9-])`, "gi");
  const found = [];
  let m;
  while ((m = re.exec(norm)) !== null) {
    const matchedStem = m[2];
    for (const [stem, label] of BOSS_ABILITY_PREFIXES) {
      if (matchedStem === stem) {
        const canonical = label === "Тащащий" ? "Тащущий" : label;
        if (!found.includes(canonical)) found.push(canonical);
        break;
      }
    }
  }
  return found;
}

export function detectExplicitLevel(text) {
  if (!text) return null;
  const cleaned = text.replace(
    /(?:геро[йяюем]|героин[яиюей]|питом[ец][а-яё]*|торгов[ец][а-яё]*)\s+[1-4]\s*-?(?:го|й|ого)?\s*уровн/gi,
    " "
  );
  const p1 = /(?:босс[а-яё]*|монстр[а-яё]*|твар[а-яё]*|страж[а-яё]*|левиафан[а-яё]*|рейд-?босс[а-яё]*|мини-?босс[а-яё]*)\s+(?:[^\d\n]{0,20}?\s)?([1-4])\s*-?(?:го|й|ого)?\s*уровн/i;
  const p2 = /(?:^|[^а-яё0-9])([1-4])\s*-?(?:го|ого)?\s*уровня(?![^\S\r\n]*(?:подземел|лабиринт|этаж|данж))/i;
  const p3 = /(?:^|[^а-яё0-9])([1-4])\s*(?:способност[ией]|абилк[иа]?|абил)/i;
  for (const re of [p1, p2, p3]) {
    const m = re.exec(cleaned);
    if (m) return Number(m[1]);
  }
  if (/одноабил|однопалуб|единичк/i.test(cleaned)) return 1;
  if (/двухабил|двухпалуб|двойк/i.test(cleaned)) return 2;
  if (/тр[её]хабил|тр[её]хпалуб|тройк/i.test(cleaned)) return 3;
  if (/четыр[её]хабил|четыр[её]хпалуб/i.test(cleaned)) return 4;
  return null;
}

const VICTORY_RE = /(?:повержен|победил|одолел|прикончил|добыл[а-яё]*\s+запчаст|получил[а-яё]*\s+реликви|поверг|пал\s+под\s+ударами|улеп[её]тыва|сбежал)/i;
const COMBAT_HINT_RE = /(?:босс|левиафан|твар[ьиюей]|чудищ|чудовищ|страж|напал|атаковал|встретил|столкнул|схватил|преградил|всплыл|вынырнул|выскочил|вылез|поджида|подстерег|удар|париру|отбива|способност|абил|взрыва|зовет|зовёт|глушит|лечит)/i;

function extractRawBossPhrase(diary) {
  if (!diary) return null;
  const patterns = [
    /(?:босс(?:-монстр)?|рейд-?босс|левиафан|чудищ[еа]|чудовищ[еа]|страж)\s+(?:по имени\s+|по прозвищу\s+|—\s*|-\s*)?([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9 -]{2,55})/,
    /(?:встретил(?:ся|ись)?\s+с|столкнул(?:ся|ись)?\s+с|напал(?:а|о|и)?\s+|атаковал(?:а|о|и)?\s+|преградил(?:а|и)?\s+путь\s+|схватил(?:ся|ись)?\s+с|нарвал(?:ся|ись)?\s+на|напорол(?:ся|ись)?\s+на|сража[ею]тся\s+с|отбива[ею]тся\s+от)\s+([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9 -]{2,55})/,
  ];
  for (const re of patterns) {
    const m = re.exec(diary);
    if (m) {
      const candidate = m[1].replace(/[.,!?;:\n()«»"'].*$/, "").replace(/^[ -—]+|[ -—]+$/g, "");
      if (candidate.length >= 3) return candidate;
    }
  }
  return null;
}

export function analyzeHeroState(payload) {
  const hasPrivateFields = ["diary_last", "fight_type", "arena_fight", "health", "godpower"].some(
    (k) => Object.prototype.hasOwnProperty.call(payload, k)
  );
  const fightType = payload.fight_type ? String(payload.fight_type).trim().toLowerCase() : null;
  const arenaFight = Boolean(payload.arena_fight);
  const diaryLast = String(payload.diary_last || "").trim();

  const catalogHit = diaryLast ? detectCatalogBoss(diaryLast) : null;
  const abilities = diaryLast ? detectAbilities(diaryLast) : [];
  const explicitLevel = diaryLast ? detectExplicitLevel(diaryLast) : null;

  const bossName = catalogHit ? catalogHit.name : extractRawBossPhrase(diaryLast);
  let bossLevel = null;
  if (explicitLevel !== null) bossLevel = explicitLevel;
  else if (catalogHit) bossLevel = catalogHit.level;
  else if (abilities.length >= 1 && abilities.length <= 4) bossLevel = abilities.length;

  const isPostFight = Boolean(diaryLast && VICTORY_RE.test(diaryLast));
  const isSurfaceBoss = fightType === "boss" || fightType === "boss_m";
  const isCombatHint = Boolean(
    isSurfaceBoss || catalogHit || abilities.length || explicitLevel !== null || (diaryLast && COMBAT_HINT_RE.test(diaryLast))
  );
  const isBossFight = Boolean(
    (ALL_FIGHT_TYPES.includes(fightType) || (arenaFight && (catalogHit || abilities.length || explicitLevel !== null))) &&
      !isPostFight
  );

  return {
    heroName: String(payload.name || "Герой"),
    godName: String(payload.godname || ""),
    heroLevel: typeof payload.level === "number" ? payload.level : null,
    health: typeof payload.health === "number" ? payload.health : null,
    maxHealth: typeof payload.max_health === "number" ? payload.max_health : null,
    quest: payload.quest ? String(payload.quest).trim() : null,
    fightType,
    arenaFight,
    diaryLast,
    bossName,
    bossLevel,
    abilities,
    isBossFight,
    isCombatSignal: isCombatHint && !isPostFight,
    isPostFight,
    hasPrivateFields,
  };
}

export function evaluateFilters(encounter, {
  enabledFightTypes,
  nameFilters,
  levelFilters,
  filterMode = "smart",
  notifyUnknownEntry = false,
  isFightEntry = false,
}) {
  if (!encounter.isBossFight) return { shouldNotify: false, matchedNames: [], matchedLevels: [], reason: "not_in_boss_fight" };
  if (encounter.fightType && !enabledFightTypes.includes(encounter.fightType)) {
    return { shouldNotify: false, matchedNames: [], matchedLevels: [], reason: "fight_type_disabled" };
  }

  const matchedNames = nameFilters.filter((nf) => matchesBossName(nf, encounter.bossName, encounter.diaryLast));
  const matchedLevels = levelFilters.filter((lvl) => encounter.bossLevel !== null && encounter.bossLevel === lvl);
  const hasAnyFilter = nameFilters.length > 0 || levelFilters.length > 0;
  const isFilterHit = matchedNames.length > 0 || matchedLevels.length > 0;

  if ((encounter.fightType === "dungeon" || encounter.fightType === "sail") && !encounter.isCombatSignal && !isFilterHit) {
    if (!(notifyUnknownEntry && isFightEntry)) {
      return { shouldNotify: false, matchedNames: [], matchedLevels: [], reason: "non_combat_step" };
    }
  }

  if (filterMode === "all") {
    return { shouldNotify: true, matchedNames, matchedLevels, reason: isFilterHit ? "all_mode_match" : "all_mode" };
  }
  if (!hasAnyFilter) {
    return { shouldNotify: true, matchedNames: [], matchedLevels: [], reason: "no_filters_any_boss" };
  }
  if (isFilterHit) {
    return { shouldNotify: true, matchedNames, matchedLevels, reason: "filter_match" };
  }
  if (filterMode === "smart" && notifyUnknownEntry && isFightEntry && !encounter.bossName && encounter.bossLevel === null) {
    return { shouldNotify: true, matchedNames: [], matchedLevels: [], reason: "unknown_fight_entry" };
  }
  return { shouldNotify: false, matchedNames: [], matchedLevels: [], reason: "filter_mismatch" };
}
