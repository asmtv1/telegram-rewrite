# testovoe3 Telegram Rewrite App

Full-stack приложение: React + TypeScript frontend, FastAPI backend, Postgres, Telethon и OpenAI-compatible LLM API.

Приложение читает Telegram-посты, переписывает текст по пользовательскому промпту и публикует результат в другой канал. Поддерживаются посты с картинками: можно оставить изображения из исходного поста, убрать их перед публикацией или добавить свои картинки через интерфейс.

## Рабочая цепочка

### 1. Забираем пост из исходного канала

Пользователь входит в приложение и подключает свой Telegram-аккаунт через Telethon.

После подключения он указывает исходный канал в поле `Исходный канал`, например:

```text
@source_channel
```

Когда пользователь нажимает `Загрузить посты`, backend через Telethon обращается к Telegram, читает последние сообщения из указанного канала и выбирает текстовые посты. Если у поста есть изображения, backend скачивает их в media storage и показывает вместе с текстом.

Загруженные посты сохраняются в Postgres и отображаются в интерфейсе. Пользователь выбирает один пост из списка для дальнейшей обработки.

### 2. Обрабатываем пост по промпту

Для выбранного поста в интерфейсе показывается оригинальный текст.

Пользователь вводит промпт, например:

```text
Перепиши пост живее и короче, сохрани смысл.
```

Когда пользователь нажимает `Переписать`, frontend отправляет на backend:

- id выбранного поста;
- оригинальный текст поста;
- промпт пользователя.

Backend отправляет оригинальный текст и промпт в настроенный LLM provider. В ответ приходит готовый переписанный текст.

Результат сохраняется в Postgres и показывается в поле `Результат`. Перед публикацией пользователь может вручную отредактировать текст.

### 3. Публикуем результат в другой канал

Пользователь указывает целевой канал в поле `Канал для публикации`, например:

```text
@target_channel
```

После проверки текста пользователь нажимает `Опубликовать`.

Backend через тот же подключённый Telethon-аккаунт отправляет готовый текст в целевой Telegram-канал. Если выбраны картинки, они публикуются вместе с постом; пользователь может использовать исходные изображения, загруженные вручную изображения или их комбинацию.

После успешной публикации у поста обновляется статус, сохраняется время публикации, а запись появляется в истории обработанных постов.

Повторная публикация того же результата защищена от случайного дубля: если текст, target channel и выбранные изображения не изменились после успешной публикации, интерфейс блокирует кнопку `Опубликовать`, а backend дополнительно отклоняет такой повтор как duplicate publish.

## Технические гарантии

### Каналы Telegram

В полях source/target можно указывать канал в привычном для пользователя виде:

- `@channel_name`;
- `channel_name`;
- `https://t.me/channel_name`;
- `https://t.me/channel_name/123`;
- приватные ссылки вида `t.me/c/<id>/...`;
- числовой id канала в формате `-100...`.

Перед обращением к Telethon backend нормализует значение канала и использует единый формат для проверки доступа, чтения истории и публикации.

Для сохранённых постов backend хранит стабильный `source_channel_id`. Поэтому один и тот же канал не создаёт дубликаты, если пользователь в разные моменты вводит `@channel_name`, `t.me/channel_name` или числовой id.

### Ошибки Telegram

Telegram-ошибки возвращаются в API как понятные HTTP-статусы:

- `404` - канал не найден или указан некорректно;
- `403` - нет доступа к source channel или нет прав публикации в target channel;
- `429` - Telegram попросил подождать из-за FloodWait;
- `409` - такой же результат уже опубликован и payload не менялся;
- `503` - Telegram-сессия не создана, истекла или недействительна;
- `502` - неожиданный сбой Telegram-слоя.

Ошибки этапов сохраняются раздельно:

- `rewrite_error` - сбой LLM-рерайта, текст ошибки сохраняется в `error_message`;
- `publish_error` - сбой отправки в Telegram, текст ошибки сохраняется в `error_message`;
- validation-ошибки до отправки, например пустой текст, некорректные media URL или duplicate publish, не перезаписывают успешный статус поста.

При ошибке публикации выбранный target channel, итоговый текст, статус `publish_error` и текст ошибки сохраняются в Postgres, чтобы попытку можно было увидеть в истории и повторить после исправления причины.

### Текст перед публикацией

Рерайт и ручной результат перед публикацией проходят серверную очистку:

- убираются `@упоминания` Telegram-каналов;
- убираются ссылки вида `t.me/...`, `telegram.me/...`, `telegram.org/...`;
- сохраняются обычные e-mail адреса;
- удаляются типовые технические обёртки LLM-ответа: `<think>...</think>`, преамбулы, markdown code fence и внешние кавычки.

Публикация в Telegram отправляется с `parse_mode=None`, чтобы markdown-разметка из чужого текста не превращалась в скрытые ссылки или не ломала итоговый пост.

### LLM provider

Рерайт работает через OpenAI-compatible интерфейс. Доступные режимы:

- `LLM_PROVIDER=deepseek` - дефолтный режим, использует `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`;
- `LLM_PROVIDER=openai_compatible` - любой совместимый endpoint, использует `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`;
- `LLM_PROVIDER=ollama` - локальный Ollama endpoint `/v1`, API key не требуется.

Prompt для LLM отделяет пользовательскую инструкцию от исходного Telegram-текста маркерами `<<<ТЕКСТ>>>` и `<<<КОНЕЦ>>>`. Исходный текст трактуется как данные, поэтому инструкции внутри чужого поста не должны управлять поведением модели.

### Лимиты Telegram

Backend учитывает лимиты Telegram:

- текстовые публикации режутся на части до `4096` символов;
- публикации с картинками отправляются через `send_file(..., caption=...)`, подпись ограничивается `1024` символами;
- длинная подпись к картинке обрезается по границе предложения, если такая граница есть.

### CI/CD

В репозитории есть GitHub Actions pipeline `.github/workflows/deploy.yml`.

Pipeline на каждый push в `main`:

- устанавливает backend-зависимости и запускает `pytest`;
- устанавливает frontend-зависимости через `npm ci`;
- собирает frontend через `npm run build`;
- валидирует обязательные GitHub Secrets для production;
- упаковывает проект и доставляет архив на VPS;
- запускает `docker compose --env-file .env up -d --build --remove-orphans`;
- делает smoke check production health endpoint `https://testovoe3.gafus.ru/api/health`.

## Итоговая проверка

Проект считается рабочим, если можно пройти весь сценарий без ручных действий вне приложения:

1. Войти в приложение.
2. Подключить Telegram-аккаунт.
3. Указать исходный канал.
4. Загрузить посты.
5. Выбрать пост.
6. Ввести промпт.
7. Получить переписанный текст.
8. При необходимости отредактировать результат.
9. Указать целевой канал.
10. Опубликовать пост в другой Telegram-канал.

## Локальный запуск

1. Скопируйте `.env.example` в `.env`.
2. Заполните `POSTGRES_PASSWORD`, `SESSION_SECRET`, `APP_ENCRYPTION_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
3. Если нужен реальный rewrite, заполните настройки выбранного LLM provider. Для дефолтного режима достаточно `DEEPSEEK_API_KEY`. Войти в приложение можно и без него.
4. Запустите:

```bash
docker compose up --build
```

Приложение будет доступно через Caddy на `http://localhost`, backend healthcheck: `http://localhost/api/health`.

### Локальный запуск без Docker

Этот вариант удобен для быстрой проверки интерфейса и backend без Postgres container. Данные, медиа и Telegram session files будут лежать в `.local-runtime/`.

1. Один раз подготовьте backend virtualenv:

```bash
python3 -m venv /tmp/testovoe3-venv
/tmp/testovoe3-venv/bin/pip install -r backend/requirements.txt
```

2. Запустите backend из корня проекта:

```bash
mkdir -p .local-runtime/sessions .local-runtime/media

PYTHONPATH=backend \
SESSION_SECRET=local-dev-session-secret \
DATABASE_URL=sqlite+aiosqlite:///$(pwd)/.local-runtime/app.db \
TELEGRAM_SESSIONS_DIR=$(pwd)/.local-runtime/sessions \
MEDIA_DIR=$(pwd)/.local-runtime/media \
MEDIA_URL_PREFIX=/media \
/tmp/testovoe3-venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Healthcheck:

```text
http://127.0.0.1:8000/api/health
```

3. В другом терминале запустите frontend:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Откройте:

```text
http://127.0.0.1:5173/
```

Для этого режима всё равно нужен заполненный корневой `.env` с `APP_ENCRYPTION_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` и настройками выбранного LLM provider для реального рерайта. Telegram-аккаунт подключается через UI заново, потому что session files хранятся отдельно в `.local-runtime/sessions`.

Тестовые app-логины:

- `прислал лично`

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

## API

| Method | Path | Auth | Назначение |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Нет | Healthcheck: DB, Telegram app credentials/session storage, LLM provider/model/configured. |
| `POST` | `/api/auth/login` | Нет | Вход в приложение по app user/password. |
| `POST` | `/api/auth/logout` | Да | Выход из приложения. |
| `GET` | `/api/auth/me` | Да | Текущий app user. |
| `GET` | `/api/telegram/status` | Да | Статус подключения Telegram-аккаунта текущего app user. |
| `POST` | `/api/telegram/send-code` | Да | Отправить Telegram login code на телефон. |
| `POST` | `/api/telegram/sign-in` | Да | Подтвердить Telegram login code. |
| `POST` | `/api/telegram/sign-in-password` | Да | Подтвердить Telegram 2FA password, если он включён. |
| `POST` | `/api/telegram/logout` | Да | Удалить Telegram credentials/session текущего app user. |
| `GET` | `/api/posts` | Да | Загрузить страницу постов из source channel, сохранить/обновить их в БД. |
| `GET` | `/api/posts/history` | Да | История переписанных, опубликованных и ошибочных постов. |
| `POST` | `/api/posts/{post_id}/rewrite` | Да | Переписать выбранный пост через LLM provider. Ошибка LLM возвращается как HTTP `502` и сохраняется в посте со статусом `rewrite_error`. |
| `POST` | `/api/posts/{post_id}/media` | Да | Загрузить свои картинки для выбранного поста. |
| `POST` | `/api/posts/{post_id}/publish` | Да | Опубликовать текст и выбранные картинки в target channel. Ошибка отправки сохраняется со статусом `publish_error`; повтор того же текста, канала и media после успешной публикации возвращает HTTP `409`. |

## Ограничения

- Поддерживаются текстовые Telegram-сообщения и изображения из постов.
- Видео не скачиваются и не публикуются.
- Опросы, документы, audio/video и прочие нестандартные media-типы пропускаются.
- Ручная загрузка media принимает только изображения.
- За один upload-запрос можно добавить до 2 изображений.
- Пользователь должен состоять в source channel.
- Для target channel нужны права публикации.
- Текстовая публикация ограничена Telegram-лимитом `4096` символов на сообщение.
- Caption при публикации с картинками ограничен Telegram-лимитом `1024` символа.
- Telegram session files чувствительны; volume `telegram_sessions` нельзя публиковать или коммитить.
- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` хранятся только в `.env`; пользовательские Telegram session files остаются в volume `telegram_sessions`.
