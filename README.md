# Godville Boss Telegram Bot + Mini App

Telegram-бот и **Telegram Mini App** для отслеживания встреч с боссами в игре **Годвилль** через официальный приватный API (`https://godville.net/gods/api/<имя_бога>/<токен>`).

Уведомления приходят, когда ваш герой встречает босса, подходящего **по заданному имени ИЛИ по заданному уровню (`1`–`4` / число способностей)** — либо любого босса, если фильтры пусты.

---

## Что внутри

* **`webapp/`** — Telegram Mini App (адаптация под светлую/тёмную тему Telegram, выбор уровней 1–4, ручной ввод имён и каталог боссов подземелий 1–4 ур., типы боёв `dungeon`/`sail`/`boss`/`boss_m`, режимы `Умный`/`Строгий`/`Все боссы`).
* **`cloudflare-worker/`** — полностью бесплатный serverless-вариант **24/7 без ПК и без банковской карты** (Cloudflare Workers + D1 SQLite + Cron каждую минуту + встроенный Mini App и webhook).
* **`src/godville_bot/`** — версия на **Python (`aiogram` 3.x + `aiohttp`)** со встроенным сервером для Mini App и SQLite.
* **Поддержка GitHub Pages** — папку `webapp/` можно выложить на GitHub Pages через веб-интерфейс Actions (или раздавать прямо из `cloudflare-worker/`).

---

## Может ли бот крутиться на GitHub?

* **GitHub Pages — да, идеально подходит для Mini App** (бесплатный HTTPS-хостинг 24/7 для папки `webapp/`).
* **GitHub Actions — нет, для 24/7 бота не подходит:**
  * Cron в GitHub Actions запускается не чаще ~1 раза в 5 минут и при нагрузке задерживается на 10–30+ минут (встречи с боссами будут пропускаться).
  * Нельзя держать постоянный процесс (лимит времени и запрет в Terms of Service GitHub на использование Actions как 24/7 хостинга серверов), плюс расписания автоматически отключаются через 60 дней без коммитов.
  * Для интерактивных команд и Mini App всё равно нужен постоянно доступный сервер/webhook.

---

## Способ 1 (рекомендуется): Бесплатно 24/7 на Cloudflare Workers

Бесплатный тариф Cloudflare Workers включает:
* **Cron Trigger `* * * * *` (каждую 1 минуту)** — 1 440 запусков/сутки из 100 000 бесплатных.
* **D1 SQLite** (5 млн чтений и 100 тыс. записей в сутки) — бот пишет в базу только при изменении состояния.
* **Встроенный HTTPS-хостинг Mini App** из папки `webapp/`.
* **Карта не требуется.**

### Пошаговый деплой в Cloudflare

1. Установите Node.js (LTS) и авторизуйтесь в Cloudflare:
   ```bash
   cd cloudflare-worker
   npm install
   npx wrangler login
   ```
2. Создайте бесплатную базу D1:
   ```bash
   npx wrangler d1 create godville-boss-db
   ```
   Скопируйте выданный `database_id` в `cloudflare-worker/wrangler.toml` вместо `REPLACE_WITH_YOUR_D1_DATABASE_ID`.
3. Инициализируйте таблицу:
   ```bash
   npm run db:init
   ```
4. Задайте секреты в Cloudflare (токен бота и секрет вебхука):
   ```bash
   npx wrangler secret put BOT_TOKEN
   npx wrangler secret put WEBHOOK_SECRET
   ```
   *(В `WEBHOOK_SECRET` придумайте любую случайную длинную строку без пробелов.)*
5. Задеплойте Worker:
   ```bash
   npm run deploy
   ```
   Вы получите адрес вида `https://godville-boss-bot.<ваш-поддомен>.workers.dev`.
6. Привяжите webhook Telegram (подставьте свой `<BOT_TOKEN>`, `<WORKER_URL>` и `<WEBHOOK_SECRET>`):
   ```bash
   curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url":"<WORKER_URL>/telegram/webhook","secret_token":"<WEBHOOK_SECRET>"}'
   ```
7. *(Опционально)* Поставьте Mini App на кнопку меню в Telegram:
   ```bash
   curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setChatMenuButton" \
     -H "Content-Type: application/json" \
     -d '{"menu_button":{"type":"web_app","text":"Фильтры","web_app":{"url":"<WORKER_URL>/"}}}'
   ```

Готово — бот и Mini App работают 24/7 бесплатно и независимо от вашего ПК.

---

## Способ 2: Python-версия (локально, Docker, VPS или бесплатный Python-хостинг)

Подходит для **Oracle Cloud Always Free VPS**, **Kerit Cloud** (бесплатный контейнер без сна), **Hugging Face Spaces (Docker)** или домашнего ПК/сервера:

1. Скопируйте `.env.example` в `.env` и заполните `BOT_TOKEN`.
2. Если Mini App выложен на **GitHub Pages**, просто укажите его URL в `WEBAPP_URL=https://<username>.github.io/<repo>/` (бот автоматически передаст текущие настройки через `?state=` и примет сохранённые через `tg.sendData`).
   Либо, если Python-контейнер доступен по HTTPS (например, Hugging Face Spaces / свой домен), укажите ваш HTTPS URL в `WEBAPP_URL` — тогда Mini App откроется в режиме Live API напрямую через встроенный сервер (`WEBAPP_PORT=8080`).
3. Локальный запуск (Windows PowerShell):
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   $env:PYTHONPATH = "src"
   python -m godville_bot.main
   ```
   Или через Docker:
   ```bash
   docker compose up -d --build
   ```

---

## Команды бота

* `/start` — приветствие и меню
* `/setup ИмяБога ВашТокен` — привязать героя к приватному API Годвилля
* `/app` — открыть Telegram Mini App
* `/filters` (`/settings`) — настройка inline-кнопками в чате
* `/addname Днищеброд, Великотушный` — добавить имена боссов
* `/delname Днищеброд` — удалить имя
* `/clearnames` — очистить имена
* `/levels 2 3` — фильтровать по уровням босса (`1`–`4`; `/levels clear` для сброса)
* `/status` — проверка текущего состояния героя в Годвилле
* `/pause` / `/resume` — пауза / возобновление мониторинга

---

## Запуск тестов

```powershell
pytest -v
```
