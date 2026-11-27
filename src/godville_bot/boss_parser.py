from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Supported fight types from Godville's private API.
ALL_FIGHT_TYPES: tuple[str, ...] = ("dungeon", "sail", "boss", "boss_m")

FIGHT_TYPE_LABELS: dict[str, str] = {
    "dungeon": "Подземелье",
    "sail": "Море (заплыв)",
    "boss": "Босс мини-квеста",
    "boss_m": "Наземный босс (зацеп)",
}

# Known dungeon boss catalog by level / ability count (from Godville Wiki / Encyclobogia).
KNOWN_BOSS_LEVELS: dict[str, int] = {
    # Level 1 (1 ability)
    "Агонщик": 1,
    "Берлоггер": 1,
    "Бесоподобный": 1,
    "Богохулио": 1,
    "Боссяк": 1,
    "Втунец": 1,
    "Дворфник": 1,
    "Железопитон": 1,
    "Жмотылёк": 1,
    "Зверблюд": 1,
    "Исподтишок": 1,
    "Капитулист": 1,
    "Коменданте": 1,
    "Молодожор": 1,
    "Мясье": 1,
    "Недоеда": 1,
    "Полнолунь": 1,
    "Попрощайка": 1,
    "Преподаван": 1,
    "Сэроежка": 1,
    "Танатоходец": 1,
    "Утипутник": 1,
    # Level 2 (2 abilities)
    "Болевестник": 2,
    "Бушевалье": 2,
    "Вчелобитник": 2,
    "Дракорождённый": 2,
    "Забивчивый": 2,
    "Заплутон": 2,
    "Кротограф": 2,
    "Крутюрье": 2,
    "Надиратель": 2,
    "Ничегоблин": 2,
    "Обомлев": 2,
    "Остепенитель": 2,
    "Пожорник": 2,
    "Примятель": 2,
    "Сатаняшка": 2,
    "Страшник": 2,
    "Телоранитель": 2,
    "Харчеватель": 2,
    "Черепакостник": 2,
    "Швейцарь": 2,
    # Level 3 (3 abilities)
    "Администраж": 3,
    "Амбаловень": 3,
    "Бешенец": 3,
    "Бомбуин": 3,
    "Босспитатель": 3,
    "Бревень": 3,
    "Бревнолицый": 3,
    "Великотушный": 3,
    "Всёгун": 3,
    "Втиран": 3,
    "Гарантюа": 3,
    "Гаубийца": 3,
    "Генеракл": 3,
    "Глыберал": 3,
    "Днищеброд": 3,
    "Люцемер": 3,
    "Монстрейшина": 3,
    "Нехилер": 3,
    "Отъелло": 3,
    "Разворотила": 3,
    "Скушатель": 3,
    "Танкистадор": 3,
    "Укрупье": 3,
    "Фингалист": 3,
    # Level 4 (4 abilities)
    "Глодочник": 4,
    "Данжеватель": 4,
    "Дровецкий": 4,
    "Дюжегуб": 4,
    "Лжинн": 4,
    "Лихорадий": 4,
    "Ломамонт": 4,
    "Мохнарх": 4,
    "Необходимый": 4,
    "Необык": 4,
    "Пресекач": 4,
    "Прессонаж": 4,
    "Проорк": 4,
    "Ротозевс": 4,
    "Спилист": 4,
    "Ссылач": 4,
    "Терзан": 4,
    "Упекун": 4,
    "Экзекудза": 4,
    "Ямбал": 4,
}

# Ability prefixes for boss-monsters (stem -> canonical label).
BOSS_ABILITY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("бойк", "Бойкий"),
    ("взрывн", "Взрывной"),
    ("глушащ", "Глушащий"),
    ("драпающ", "Драпающий"),
    ("золотоносн", "Золотоносный"),
    ("зовущ", "Зовущий"),
    ("крепчающ", "Крепчающий"),
    ("лучезарн", "Лучезарный"),
    ("ломающ", "Ломающий"),
    ("мощн", "Мощный"),
    ("мним", "Мнимый"),
    ("мутирующ", "Мутирующий"),
    ("неверующ", "Неверующий"),
    ("паразитирующ", "Паразитирующий"),
    ("пробивающ", "Пробивающий"),
    ("спешащ", "Спешащий"),
    ("тащущ", "Тащущий"),
    ("тащащ", "Тащащий"),
    ("творящ", "Творящий"),
    ("транжирящ", "Транжирящий"),
    ("ушаст", "Ушастый"),
)

_ABILITY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(stem) for stem, _ in BOSS_ABILITY_PREFIXES) + r")[а-яё]{1,4}\b",
    re.IGNORECASE,
)

_TOKEN_PATTERN = re.compile(r"[a-zа-яё0-9-]+", re.IGNORECASE)

# Russian inflection endings ordered longest-first for light declension normalization.
_RU_ENDINGS: tuple[str, ...] = (
    "иями",
    "ями",
    "ами",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ью",
    "ой",
    "ей",
    "ий",
    "ый",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ую",
    "юю",
    "ом",
    "ем",
    "им",
    "ым",
    "ах",
    "ях",
    "ов",
    "ев",
    "ам",
    "ям",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "и",
    "ы",
    "о",
    "ь",
)

_EXPLICIT_LEVEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:босс[а-яё]*|монстр[а-яё]*|твар[а-яё]*|страж[а-яё]*|левиафан[а-яё]*|"
        r"рейд-?босс[а-яё]*|мини-?босс[а-яё]*)\s+(?:[^\d\n]{0,20}?\s)?([1-4])\s*-?(?:го|й|ого)?\s*уровн",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([1-4])\s*-?(?:го|ого)?\s*уровня\b(?!\s*(?:подземел|лабиринт|этаж|данж))",
        re.IGNORECASE,
    ),
    re.compile(r"\b([1-4])\s*(?:способност[ией]|абилк[иа]?|абил)\b", re.IGNORECASE),
)

_WORD_LEVEL_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\bодноабил\w*\b|\bоднопалуб\w*\b|\bединичк\w*\b", re.IGNORECASE), 1),
    (re.compile(r"\bдвухабил\w*\b|\bдвухпалуб\w*\b|\bдвойк\w*\b", re.IGNORECASE), 2),
    (re.compile(r"\bтр[её]хабил\w*\b|\bтр[её]хпалуб\w*\b|\bтройк\w*\b", re.IGNORECASE), 3),
    (re.compile(r"\bчетыр[её]хабил\w*\b|\bчетыр[её]хпалуб\w*\b", re.IGNORECASE), 4),
)

_HERO_LEVEL_GUARD = re.compile(
    r"(?:геро[йяюем]|героин[яиюей]|питом[ец][а-яё]*|торгов[ец][а-яё]*)\s+[1-4]\s*-?(?:го|й|ого)?\s*уровн",
    re.IGNORECASE,
)

_BOSS_INTRO_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:босс(?:-монстр[а-яё]*|[ауое]|ом)?|рейд-?босс[а-яё]*|мини-?босс[а-яё]*|левиафан[а-яё]*|чудищ[еау]?|чудовищ[еау]?|страж[а-яё]*)\s+"
        r"(?:по имени\s+|по прозвищу\s+|—\s*|-\s*)?([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9 -]{2,55})",
    ),
    re.compile(
        r"(?:встретил(?:ся|ись)?\s+(?:с\s+)?|столкнул(?:ся|ись)?\s+с\s+|напал(?:а|о|и)?\s+|"
        r"атаковал(?:а|о|и)?\s+|преградил(?:а|и)?\s+путь\s+|схватил(?:ся|ись)?\s+с\s+|"
        r"нарвал(?:ся|ись)?\s+на\s+|напорол(?:ся|ись)?\s+на\s+|сража[ею]тся\s+с\s+|"
        r"отбива[ею]тся\s+от\s+)([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9 -]{2,55})",
    ),
)

_VICTORY_OR_END_PATTERN = re.compile(
    r"\b(?:повержен\w*|победил\w*|одолел\w*|прикончил\w*|добыл\w*\s+запчаст\w*|"
    r"получил\w*\s+реликви\w*|поверг\w*|пал\s+под\s+ударами|успел\w*\s+улепет\w*|сбежал\w*\s+с\s+пол[яе]\s+боя)\b",
    re.IGNORECASE,
)

_COMBAT_HINT_PATTERN = re.compile(
    r"\b(?:босс\w*|левиафан\w*|твар[ьиюей]\w*|чудищ\w*|чудовищ\w*|страж\w*|враг\w*|противник\w*|монстр\w*|звер[ьяюем]\w*|"
    r"напал\w*|атаковал\w*|атак\w*|встретил\w*|столкнул\w*|схватил\w*|схватк\w*|преградил\w*|"
    r"всплыл\w*|вынырнул\w*|выскочил\w*|вылез\w*|поджида\w*|подстерег\w*|"
    r"удар\w*|урон\w*|ранен\w*|париру\w*|отбива\w*|сража\w*|битв\w*|дуэл\w*|бь[её]т\w*|рычит|шипит|кусает|цапает|"
    r"способност\w*|абил\w*|взрыва\w*|зовет|зовёт|глушит|лечит\w*)\b",
    re.IGNORECASE,
)

_SENTENCE_BOUNDARY_TRIM = re.compile(r"[.,!?;:\n()«»\"'].*$")


def normalize_ru(text: str) -> str:
    """Lowercase and normalize Cyrillic 'ё' -> 'е' with collapsed whitespace."""
    return " ".join(text.lower().replace("ё", "е").split())


def tokenize_ru(text: str) -> list[str]:
    """Extract normalized alphanumeric/hyphenated word tokens."""
    return _TOKEN_PATTERN.findall(normalize_ru(text))


def russian_stem(word: str) -> str:
    """Lightweight Russian inflection stemmer safe for short boss names."""
    norm = normalize_ru(word)
    if len(norm) <= 4:
        return norm
    for ending in _RU_ENDINGS:
        if norm.endswith(ending) and len(norm) - len(ending) >= 4:
            return norm[: -len(ending)]
    return norm


def _tokens_match(filter_token: str, text_token: str) -> bool:
    if filter_token == text_token:
        return True
    f_stem = russian_stem(filter_token)
    t_stem = russian_stem(text_token)
    if len(f_stem) >= 4 and f_stem == t_stem:
        return True
    if len(filter_token) >= 5 and text_token.startswith(f_stem) and len(f_stem) >= 4:
        return True
    return False


def matches_boss_name(name_filter: str, *texts: str | None) -> bool:
    """Match a configured boss name filter against candidate texts with declension support."""
    filter_tokens = tokenize_ru(name_filter)
    if not filter_tokens:
        return False

    for text in texts:
        if not text:
            continue
        text_tokens = tokenize_ru(text)
        if not text_tokens:
            continue

        if len(filter_tokens) == 1:
            ft = filter_tokens[0]
            if any(_tokens_match(ft, tt) for tt in text_tokens):
                return True
        else:
            # All filter words must appear in sequence (or close order) in text tokens.
            n = len(filter_tokens)
            for idx in range(len(text_tokens) - n + 1):
                window = text_tokens[idx : idx + n]
                if all(_tokens_match(ft, tt) for ft, tt in zip(filter_tokens, window)):
                    return True
    return False


_CATALOG_BY_NORM: dict[str, tuple[str, int]] = {
    normalize_ru(name): (name, level) for name, level in KNOWN_BOSS_LEVELS.items()
}


def detect_catalog_boss(text: str) -> tuple[str, int] | None:
    """Find a known Godville dungeon boss in text, accounting for Russian declensions."""
    tokens = tokenize_ru(text)
    if not tokens:
        return None
    for norm_name, entry in _CATALOG_BY_NORM.items():
        if any(_tokens_match(norm_name, tok) for tok in tokens):
            return entry
    return None


def detect_abilities(text: str) -> list[str]:
    """Extract canonical boss ability prefixes from diary text."""
    seen: list[str] = []
    norm_text = normalize_ru(text)
    for match in _ABILITY_PATTERN.finditer(norm_text):
        matched_stem = match.group(1)
        for stem, label in BOSS_ABILITY_PREFIXES:
            if matched_stem == stem:
                # Normalize Тащущий/Тащащий under one canonical name so it doesn't count twice.
                canonical = "Тащущий" if label in ("Тащущий", "Тащащий") else label
                if canonical not in seen:
                    seen.append(canonical)
                break
    return seen


def detect_explicit_level(text: str) -> int | None:
    """Extract explicit boss level (1..4) from diary text."""
    if not text:
        return None
    cleaned = _HERO_LEVEL_GUARD.sub(" ", text)
    for pattern in _EXPLICIT_LEVEL_PATTERNS:
        m = pattern.search(cleaned)
        if m:
            lvl = int(m.group(1))
            if 1 <= lvl <= 4:
                return lvl
    for pattern, lvl in _WORD_LEVEL_PATTERNS:
        if pattern.search(cleaned):
            return lvl
    return None


def _extract_raw_boss_phrase(diary_last: str) -> str | None:
    if not diary_last:
        return None
    for pattern in _BOSS_INTRO_NAME_PATTERNS:
        match = pattern.search(diary_last)
        if match:
            candidate = _SENTENCE_BOUNDARY_TRIM.sub("", match.group(1)).strip(" -—")
            if len(candidate) >= 3:
                return candidate
    return None


def has_private_api_fields(payload: dict[str, Any]) -> bool:
    """Return True if the JSON payload includes private-API operational fields."""
    private_keys = ("diary_last", "fight_type", "arena_fight", "health", "godpower")
    return any(key in payload for key in private_keys)


@dataclass(frozen=True, slots=True)
class BossEncounter:
    """Parsed boss/fight state derived from a Godville hero JSON payload."""

    hero_name: str
    god_name: str
    hero_level: int | None
    health: int | None
    max_health: int | None
    quest: str | None
    fight_type: str | None
    arena_fight: bool
    diary_last: str
    boss_name: str | None
    boss_level: int | None
    abilities: tuple[str, ...] = field(default_factory=tuple)
    is_boss_fight: bool = False
    is_combat_signal: bool = False
    is_post_fight: bool = False
    has_private_fields: bool = True


def analyze_hero_state(payload: dict[str, Any]) -> BossEncounter:
    """Analyze a Godville API JSON payload for boss encounters, names, and levels."""
    has_private = has_private_api_fields(payload)
    raw_fight_type = payload.get("fight_type")
    fight_type = str(raw_fight_type).strip().lower() if raw_fight_type else None
    arena_fight = bool(payload.get("arena_fight", False))
    diary_last = str(payload.get("diary_last") or "").strip()

    catalog_hit = detect_catalog_boss(diary_last) if diary_last else None
    abilities = tuple(detect_abilities(diary_last)) if diary_last else ()
    explicit_level = detect_explicit_level(diary_last) if diary_last else None

    boss_name: str | None = None
    if catalog_hit is not None:
        boss_name = catalog_hit[0]
    else:
        boss_name = _extract_raw_boss_phrase(diary_last)

    boss_level: int | None = None
    if explicit_level is not None:
        boss_level = explicit_level
    elif catalog_hit is not None:
        boss_level = catalog_hit[1]
    elif 1 <= len(abilities) <= 4:
        boss_level = len(abilities)

    is_post_fight = bool(diary_last and _VICTORY_OR_END_PATTERN.search(diary_last))

    # Surface boss fight types always mean a boss encounter; dungeon/sail require combat/boss hints
    # unless user tracks fight entry.
    is_surface_boss = fight_type in ("boss", "boss_m")
    is_combat_hint = bool(
        is_surface_boss
        or catalog_hit is not None
        or abilities
        or explicit_level is not None
        or (diary_last and _COMBAT_HINT_PATTERN.search(diary_last))
    )
    is_boss_fight = bool(
        (fight_type in ALL_FIGHT_TYPES or (arena_fight and (catalog_hit or abilities or explicit_level)))
        and not is_post_fight
    )

    return BossEncounter(
        hero_name=str(payload.get("name") or "Герой"),
        god_name=str(payload.get("godname") or ""),
        hero_level=payload.get("level") if isinstance(payload.get("level"), int) else None,
        health=payload.get("health") if isinstance(payload.get("health"), int) else None,
        max_health=payload.get("max_health") if isinstance(payload.get("max_health"), int) else None,
        quest=str(payload.get("quest")).strip() if payload.get("quest") else None,
        fight_type=fight_type,
        arena_fight=arena_fight,
        diary_last=diary_last,
        boss_name=boss_name,
        boss_level=boss_level,
        abilities=abilities,
        is_boss_fight=is_boss_fight,
        is_combat_signal=is_combat_hint and not is_post_fight,
        is_post_fight=is_post_fight,
        has_private_fields=has_private,
    )


@dataclass(frozen=True, slots=True)
class FilterResult:
    """Outcome of evaluating a BossEncounter against user filter preferences."""

    should_notify: bool
    matched_names: tuple[str, ...] = field(default_factory=tuple)
    matched_levels: tuple[int, ...] = field(default_factory=tuple)
    reason: str = ""


def evaluate_filters(
    encounter: BossEncounter,
    *,
    enabled_fight_types: set[str] | frozenset[str] | tuple[str, ...] | list[str],
    name_filters: list[str] | tuple[str, ...],
    level_filters: list[int] | tuple[int, ...],
    filter_mode: str = "smart",
    notify_unknown_entry: bool = False,
    is_fight_entry: bool = False,
    has_pending_unknown_entry: bool = False,
) -> FilterResult:
    """Decide whether an encounter matches user's name OR level filter criteria."""
    if not encounter.is_boss_fight:
        return FilterResult(should_notify=False, reason="not_in_boss_fight")

    if encounter.fight_type and encounter.fight_type not in enabled_fight_types:
        return FilterResult(should_notify=False, reason="fight_type_disabled")

    matched_names = tuple(
        nf for nf in name_filters if matches_boss_name(nf, encounter.boss_name, encounter.diary_last)
    )
    matched_levels = tuple(
        lvl for lvl in level_filters if encounter.boss_level is not None and encounter.boss_level == lvl
    )

    has_any_filter = bool(name_filters or level_filters)
    is_filter_hit = bool(matched_names or matched_levels)

    # Inside dungeon/sail, ignore plain exploration/corridor diary lines unless a user-configured
    # filter matched directly, there is a combat/boss signal, or entry notification applies.
    if encounter.fight_type in ("dungeon", "sail") and not encounter.is_combat_signal and not is_filter_hit:
        if not ((not has_any_filter or notify_unknown_entry) and is_fight_entry):
            return FilterResult(should_notify=False, reason="non_combat_step")

    if filter_mode == "all":
        return FilterResult(
            should_notify=True,
            matched_names=matched_names,
            matched_levels=matched_levels,
            reason="all_mode_match" if is_filter_hit else "all_mode",
        )

    if not has_any_filter:
        # No custom name/level filter configured -> notify on any boss/combat encounter.
        return FilterResult(
            should_notify=True,
            reason="no_filters_any_boss",
        )

    if is_filter_hit:
        return FilterResult(
            should_notify=True,
            matched_names=matched_names,
            matched_levels=matched_levels,
            reason="filter_match",
        )

    is_unknown_details = (
        (encounter.boss_name is None and encounter.boss_level is None)
        or (bool(level_filters) and encounter.boss_level is None)
    )
    if (
        filter_mode == "smart"
        and notify_unknown_entry
        and is_fight_entry
        and is_unknown_details
    ):
        return FilterResult(
            should_notify=True,
            reason="unknown_fight_entry",
        )

    if (
        filter_mode == "smart"
        and notify_unknown_entry
        and has_pending_unknown_entry
        and encounter.boss_name is not None
        and bool(level_filters)
        and encounter.boss_level is None
    ):
        return FilterResult(
            should_notify=True,
            reason="unknown_fight_details",
        )

    return FilterResult(should_notify=False, reason="filter_mismatch")
