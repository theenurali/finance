# Telegram Finance Bot

Production-ready Telegram-бот для учета личных финансов: расходы, доходы, отчеты, CSV-экспорт, пагинация истории и готовность к SQLite/PostgreSQL.

## Возможности

- Автоматическая регистрация пользователя по Telegram ID
- Изоляция данных каждого пользователя
- Расходы и доходы через команды или кнопки категорий
- Категории: еда, транспорт, развлечения, жильё, другое
- Общая статистика, дневной и месячный отчеты
- Гибкие бюджеты: текущий месяц, день, конкретная дата, N дней, произвольный диапазон
- Учет долгов: я должен / мне должны, список активных долгов, закрытие долга
- Аналитика: проценты, топ категорий, недельный тренд, предупреждения при доле категории больше 40%
- Inline-подтверждение операций
- CSV-экспорт через `/export`
- Пагинация истории через `/history`
- Базовая защита от Telegram flood limit через `AIORateLimiter`
- SQLAlchemy ORM, легко переключить SQLite на PostgreSQL
- Dockerfile и инструкции для Render, Railway, VPS/systemd

## Структура

```text
project/
├── bot/
│   ├── handlers/
│   ├── keyboards/
│   ├── middlewares/
│   └── config.py
├── database/
│   ├── models.py
│   ├── db.py
│   └── queries.py
├── services/
│   ├── analytics.py
│   └── reports.py
├── utils/
│   └── helpers.py
├── .env.example
├── requirements.txt
├── Dockerfile
├── main.py
└── README.md
```

## Быстрый старт

1. Создайте бота через [@BotFather](https://t.me/BotFather) и получите токен.

2. Создайте виртуальное окружение:

```bash
python -m venv .venv
source .venv/bin/activate
```

Для Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Установите зависимости:

```bash
pip install -r requirements.txt
```

4. Создайте `.env`:

```bash
cp .env.example .env
```

Заполните:

```env
BOT_TOKEN=ваш_telegram_token
DATABASE_URL=sqlite+aiosqlite:///./finance_bot.db
LOG_LEVEL=INFO
```

5. Запустите:

```bash
python main.py
```

При первом запуске таблицы SQLite будут созданы автоматически.

## Команды бота

```text
/start   - регистрация и помощь
/add     - добавить расход
/income  - добавить доход
/stats   - общая статистика
/month   - отчет за текущий месяц
/day     - расходы за сегодня
/top     - топ категорий расходов
/budget  - бюджеты и лимиты на период
/debt    - долги
/history - история операций с пагинацией
/export  - CSV выгрузка
/reset   - удалить свои операции
```

Быстрый ввод:

```text
/add 2000 еда
/income 5000 зарплата
```

Или нажмите категорию на ReplyKeyboard и затем отправьте сумму.

## Бюджеты

Команда `/budget` без аргументов покажет активные бюджеты и сколько уже потрачено за каждый период.

Примеры:

```text
/budget 120000
/budget day 5000
/budget day 2026-05-10 7000
/budget month 2026-05 150000
/budget days 10 40000
/budget custom 2026-05-01 2026-05-15 50000
/budget delete 2
```

`/budget 120000` по умолчанию ставит лимит на текущий месяц.

## Долги

Примеры:

```text
/debt я 5000 Али обед
/debt мне 10000 Данияр заем
/debt list
/debt paid 3
```

Долги хранятся отдельно от расходов и доходов, чтобы не ломать финансовую статистику.

## PostgreSQL

Код использует SQLAlchemy ORM и async engine. Для перехода на PostgreSQL достаточно заменить `DATABASE_URL`:

```env
DATABASE_URL=postgresql+asyncpg://finance_user:strong_password@localhost:5432/finance_bot
```

Для коммерческого проекта рекомендуется добавить Alembic-миграции перед активной разработкой схемы.

## Docker

Сборка:

```bash
docker build -t finance-telegram-bot .
```

Запуск:

```bash
docker run --env-file .env --name finance-bot finance-telegram-bot
```

Для SQLite в Docker добавьте volume:

```bash
docker run --env-file .env -v finance_data:/app/data finance-telegram-bot
```

И задайте:

```env
DATABASE_URL=sqlite+aiosqlite:////app/data/finance_bot.db
```

## Deploy: Render.com

1. Загрузите проект в GitHub.
2. Создайте новый `Web Service` или `Background Worker`.
3. Runtime: Docker или Python 3.
4. Build command для Python:

```bash
pip install -r requirements.txt
```

5. Start command:

```bash
python main.py
```

6. Добавьте environment variables:

```text
BOT_TOKEN
DATABASE_URL
LOG_LEVEL
```

7. Для production лучше использовать Render PostgreSQL и `postgresql+asyncpg://...`.

## Deploy: Railway

1. Создайте новый Railway project из GitHub repo.
2. Добавьте PostgreSQL plugin.
3. В Variables добавьте:

```text
BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://...
LOG_LEVEL=INFO
```

4. Start command:

```bash
python main.py
```

Railway сам перезапустит процесс при падении.

## Deploy: VPS Linux + systemd

1. Установите зависимости:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv git
```

2. Склонируйте проект:

```bash
git clone <repo-url> /opt/finance-bot
cd /opt/finance-bot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

3. Заполните `/opt/finance-bot/.env`.

4. Создайте systemd unit:

```ini
[Unit]
Description=Telegram Finance Bot
After=network.target

[Service]
WorkingDirectory=/opt/finance-bot
EnvironmentFile=/opt/finance-bot/.env
ExecStart=/opt/finance-bot/.venv/bin/python /opt/finance-bot/main.py
Restart=always
RestartSec=5
User=www-data

[Install]
WantedBy=multi-user.target
```

Сохраните как `/etc/systemd/system/finance-bot.service`.

5. Запустите:

```bash
sudo systemctl daemon-reload
sudo systemctl enable finance-bot
sudo systemctl start finance-bot
sudo systemctl status finance-bot
```

Логи:

```bash
journalctl -u finance-bot -f
```

## Production notes

- Для одного процесса polling достаточно встроенного in-memory rate-limit и `AIORateLimiter`.
- При горизонтальном масштабировании используйте webhook, Redis rate-limit и PostgreSQL.
- Для развивающейся схемы добавьте Alembic.
- Для мониторинга добавьте healthcheck, Sentry и алерты по systemd/Docker logs.
