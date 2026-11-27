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
  const abilities = detectAbilities("Бойкий Мощный Пробивающий Мутирующий Ушастый Левиафан");
  assert.deepEqual(abilities, ["Бойкий", "Мощный", "Пробивающий", "Мутирующий", "Ушастый"]);
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

test("unknown-level boss entry with notifyUnknownEntry and mid-fight escape guard", () => {
  const escaping = analyzeHeroState({
    name: "Герой",
    arena_fight: true,
    fight_type: "boss_m",
    diary_last: "Встретил босса Чумохода, который пытается улепётывать с поля боя!",
  });
  assert.equal(escaping.isPostFight, false);
  assert.equal(escaping.bossName, "Чумохода");
  assert.equal(escaping.bossLevel, null);

  const withUnknownOn = evaluateFilters(escaping, {
    enabledFightTypes: ["dungeon", "sail", "boss", "boss_m"],
    nameFilters: ["Проорк"],
    levelFilters: [2, 3, 4],
    filterMode: "smart",
    notifyUnknownEntry: true,
    isFightEntry: true,
  });
  assert.equal(withUnknownOn.shouldNotify, true);
  assert.equal(withUnknownOn.reason, "unknown_fight_entry");

  const lvl1Catalog = analyzeHeroState({
    name: "Герой",
    arena_fight: true,
    fight_type: "boss_m",
    diary_last: "Напал на Агонщика!",
  });
  const suppressedLvl1 = evaluateFilters(lvl1Catalog, {
    enabledFightTypes: ["dungeon", "sail", "boss", "boss_m"],
    nameFilters: ["Проорк"],
    levelFilters: [2, 3, 4],
    filterMode: "smart",
    notifyUnknownEntry: true,
    isFightEntry: true,
  });
  assert.equal(suppressedLvl1.shouldNotify, false);
  assert.equal(suppressedLvl1.reason, "filter_mismatch");

  const execuza = analyzeHeroState({
    name: "Герой",
    arena_fight: true,
    fight_type: "dungeon",
    diary_last: "Встретили Экзекудзу!",
  });
  assert.equal(execuza.bossName, "Экзекудза");
  assert.equal(execuza.bossLevel, 4);

  const followUp = evaluateFilters(escaping, {
    enabledFightTypes: ["dungeon", "sail", "boss", "boss_m"],
    nameFilters: ["Проорк"],
    levelFilters: [2, 3, 4],
    filterMode: "smart",
    notifyUnknownEntry: true,
    isFightEntry: false,
    hasPendingUnknownEntry: true,
  });
  assert.equal(followUp.shouldNotify, true);
  assert.equal(followUp.reason, "unknown_fight_details");
});
