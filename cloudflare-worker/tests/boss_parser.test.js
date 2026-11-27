import test from "node:test";
import assert from "node:assert/strict";
import {
  analyzeHeroState,
  detectAbilities,
  detectExplicitLevel,
  evaluateFilters,
  matchesBossName,
} from "../src/boss_parser.js";

test("catalog boss detection with Russian declensions", () => {
  const enc = analyzeHeroState({
    name: "Сэр Тест",
    level: 80,
    health: 70,
    max_health: 100,
    arena_fight: true,
    fight_type: "dungeon",
    diary_last: "Отряд столкнулся с Днищебродом у самой сокровищницы.",
  });
  assert.equal(enc.hasPrivateFields, true);
  assert.equal(enc.isBossFight, true);
  assert.equal(enc.bossName, "Днищеброд");
  assert.equal(enc.bossLevel, 3);
});

test("abilities counting and yo normalization", () => {
  const abilities = detectAbilities("Бойкий Мощный Пробивающий Левиафан");
  assert.deepEqual(abilities, ["Бойкий", "Мощный", "Пробивающий"]);
  assert.equal(detectExplicitLevel("Герой 3 уровня перешёл на 2 уровень подземелья."), null);
  assert.equal(detectExplicitLevel("Перед нами босс 3-го уровня!"), 3);
  assert.equal(matchesBossName("Дракорожденный", "Дракорождённый"), true);
  assert.equal(matchesBossName("Лис", "Спилист"), false);
});

test("evaluateFilters OR semantics (name or level)", () => {
  const enc = analyzeHeroState({
    name: "Герой",
    arena_fight: true,
    fight_type: "dungeon",
    diary_last: "Навстречу вышел Харчеватель!",
  });

  const byName = evaluateFilters(enc, {
    enabledFightTypes: ["dungeon", "sail"],
    nameFilters: ["Харчеватель"],
    levelFilters: [3],
  });
  assert.equal(byName.shouldNotify, true);

  const byLevel = evaluateFilters(enc, {
    enabledFightTypes: ["dungeon", "sail"],
    nameFilters: ["Днищеброд"],
    levelFilters: [2],
  });
  assert.equal(byLevel.shouldNotify, true);

  const neither = evaluateFilters(enc, {
    enabledFightTypes: ["dungeon", "sail"],
    nameFilters: ["Днищеброд"],
    levelFilters: [3],
  });
  assert.equal(neither.shouldNotify, false);

  const anyEntry = evaluateFilters(
    analyzeHeroState({
      name: "Герой",
      arena_fight: true,
      fight_type: "dungeon",
      diary_last: "Спустился вниз по лестнице.",
    }),
    {
      enabledFightTypes: ["dungeon", "sail"],
      nameFilters: [],
      levelFilters: [],
      isFightEntry: true,
    }
  );
  assert.equal(anyEntry.shouldNotify, true);
});
