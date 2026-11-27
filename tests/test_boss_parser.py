from __future__ import annotations

from godville_bot.boss_parser import (
    analyze_hero_state,
    detect_abilities,
    detect_explicit_level,
    evaluate_filters,
    matches_boss_name,
)


def test_catalog_boss_detection_with_russian_declensions() -> None:
    payload = {
        "name": "Сэр Тест",
        "godname": "Тестобог",
        "level": 80,
        "health": 70,
        "max_health": 100,
        "arena_fight": True,
        "fight_type": "dungeon",
        "diary_last": "Отряд вплотную столкнулся с Днищебродом у самой сокровищницы.",
    }
    encounter = analyze_hero_state(payload)
    assert encounter.has_private_fields is True
    assert encounter.is_boss_fight is True
    assert encounter.boss_name == "Днищеброд"
    assert encounter.boss_level == 3


def test_yo_normalization_and_abilities_count_level() -> None:
    diary = "На горизонте возник Бойкий Мощный Пробивающий Левиафан Морской!"
    abilities = detect_abilities(diary)
    assert abilities == ["Бойкий", "Мощный", "Пробивающий"]

    payload = {
        "name": "Капитан",
        "arena_fight": True,
        "fight_type": "sail",
        "diary_last": diary,
    }
    encounter = analyze_hero_state(payload)
    assert encounter.boss_level == 3
    assert encounter.abilities == ("Бойкий", "Мощный", "Пробивающий")


def test_yo_catalog_match_for_drakorozhdenny() -> None:
    payload = {
        "name": "Герой",
        "arena_fight": True,
        "fight_type": "dungeon",
        "diary_last": "Внезапно из темноты напал Дракорождённый!",
    }
    encounter = analyze_hero_state(payload)
    assert encounter.boss_name == "Дракорождённый"
    assert encounter.boss_level == 2
    assert matches_boss_name("Дракорожденный", encounter.boss_name, encounter.diary_last)


def test_explicit_level_guards_against_hero_and_floor_levels() -> None:
    assert detect_explicit_level("Герой 3 уровня перешёл на 2 уровень подземелья.") is None
    assert detect_explicit_level("Спустились на 2-й уровень лабиринта.") is None
    assert detect_explicit_level("Перед нами босс 3-го уровня с неприятной улыбкой.") == 3
    assert detect_explicit_level("Огромная тварь 2 уровня, трёхабильный страж") in (2, 3)
    assert detect_explicit_level("Появился двухабильный монстр") == 2


def test_short_name_filter_avoids_false_substring_matches() -> None:
    assert not matches_boss_name("Лис", "Спилист")
    assert matches_boss_name("Швейцарь", "Сражаемся со Швейцарем в холле")
    assert matches_boss_name("Великотушный", "Отбиваемся от Великотушного")


def test_evaluate_filters_or_semantics_name_or_level() -> None:
    payload = {
        "name": "Герой",
        "arena_fight": True,
        "fight_type": "dungeon",
        "diary_last": "Навстречу вышел Харчеватель!",
    }
    encounter = analyze_hero_state(payload)
    assert encounter.boss_name == "Харчеватель"
    assert encounter.boss_level == 2

    # Matches by name even when level filter doesn't include 2
    by_name = evaluate_filters(
        encounter,
        enabled_fight_types={"dungeon", "sail"},
        name_filters=["Харчеватель"],
        level_filters=[3],
    )
    assert by_name.should_notify is True
    assert by_name.matched_names == ("Харчеватель",)
    assert by_name.matched_levels == ()

    # Matches by level even when name filter targets another boss
    by_level = evaluate_filters(
        encounter,
        enabled_fight_types={"dungeon", "sail"},
        name_filters=["Днищеброд"],
        level_filters=[2, 3],
    )
    assert by_level.should_notify is True
    assert by_level.matched_names == ()
    assert by_level.matched_levels == (2,)

    # Neither name nor level matches
    no_match = evaluate_filters(
        encounter,
        enabled_fight_types={"dungeon", "sail"},
        name_filters=["Днищеброд"],
        level_filters=[3],
    )
    assert no_match.should_notify is False


def test_evaluate_filters_respects_fight_type_and_post_fight() -> None:
    surface_payload = {
        "name": "Герой",
        "arena_fight": True,
        "fight_type": "boss_m",
        "diary_last": "Напал Бойкий Бульдозер!",
    }
    surface_enc = analyze_hero_state(surface_payload)

    assert (
        evaluate_filters(
            surface_enc,
            enabled_fight_types={"dungeon", "sail"},
            name_filters=[],
            level_filters=[],
        ).should_notify
        is False
    )
    assert (
        evaluate_filters(
            surface_enc,
            enabled_fight_types={"dungeon", "sail", "boss_m"},
            name_filters=[],
            level_filters=[],
        ).should_notify
        is True
    )

    victory_payload = {
        "name": "Герой",
        "arena_fight": True,
        "fight_type": "dungeon",
        "diary_last": "Днищеброд повержен! Герой обыскал сундук.",
    }
    victory_enc = analyze_hero_state(victory_payload)
    assert victory_enc.is_post_fight is True
    assert victory_enc.is_boss_fight is False
    assert (
        evaluate_filters(
            victory_enc,
            enabled_fight_types={"dungeon", "sail"},
            name_filters=["Днищеброд"],
            level_filters=[3],
        ).should_notify
        is False
    )


def test_detect_missing_private_fields() -> None:
    public_only = {
        "name": "Герой",
        "godname": "Бог",
        "level": 50,
        "max_health": 120,
    }
    enc = analyze_hero_state(public_only)
    assert enc.has_private_fields is False
    assert enc.is_boss_fight is False


def test_empty_filters_notify_on_dungeon_entry_and_combat_words() -> None:
    entry = analyze_hero_state(
        {
            "name": "Герой",
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Спустился вниз по лестнице.",
        }
    )
    assert (
        evaluate_filters(
            entry,
            enabled_fight_types={"dungeon", "sail"},
            name_filters=[],
            level_filters=[],
            is_fight_entry=True,
        ).should_notify
        is True
    )

    combat = analyze_hero_state(
        {
            "name": "Герой",
            "arena_fight": True,
            "fight_type": "dungeon",
            "diary_last": "Противник рычит и готовится атаковать.",
        }
    )
    assert combat.is_combat_signal is True
    assert (
        evaluate_filters(
            combat,
            enabled_fight_types={"dungeon", "sail"},
            name_filters=[],
            level_filters=[],
            is_fight_entry=False,
        ).should_notify
        is True
    )
