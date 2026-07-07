# testovoe3 Telegram Rewrite App

Full-stack приложение: React + TypeScript frontend, FastAPI backend, Postgres, Telethon и DeepSeek OpenAI-compatible API.

## Локальный запуск

1. Скопируйте `.env.example` в `.env`.
2. Заполните `POSTGRES_PASSWORD`, `SESSION_SECRET`, `APP_ENCRYPTION_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
3. Если нужен реальный rewrite, заполните `DEEPSEEK_API_KEY`. Войти в приложение можно и без него.
4. Запустите:

```bash
docker compose up --build
```

Приложение будет доступно через Caddy на `http://localhost`, backend healthcheck: `http://localhost/api/health`.

Тестовые app-логины:

- `user1 / 12345`

Telegram-аккаунт каждый app user подключает отдельно через UI. В интерфейсе вводится только телефон, код Telegram и 2FA пароль, если он включён. `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` хранятся один раз в backend `.env`.

## Production deploy


Запуск:

```bash
docker compose up -d --build
```

Caddy сам выпустит HTTPS-сертификат, если DNS уже указывает на сервер и порты доступны.

## Проверки

Backend tests:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
```

Frontend build:

```bash
cd frontend
npm install
npm run build
```

## Ограничения

- Поддерживаются только текстовые Telegram-сообщения.
- Медиа не скачиваются и не публикуются.
- Пользователь должен состоять в source channel.
- Для target channel нужны права публикации.
- Telegram session files чувствительны; volume `telegram_sessions` нельзя публиковать или коммитить.
- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` хранятся только в `.env`; пользовательские Telegram session files остаются в volume `telegram_sessions`.
