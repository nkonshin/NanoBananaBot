# Changelog: Улучшения и рефакторинг

## Дата: 26 декабря 2025

### 1. Централизация констант в config.py

**Было:** `HIGH_COST_THRESHOLD = 4000` дублировался в 3 файлах

**Стало:** Единая переменная `config.high_cost_threshold` из ENV

**Файлы:**
- `bot/config.py` — добавлены новые настройки
- `bot/handlers/generate.py` — использует `config.high_cost_threshold`
- `bot/handlers/edit.py` — использует `config.high_cost_threshold`
- `bot/handlers/trends.py` — использует `config.high_cost_threshold`

### 2. Новые переменные окружения

| Переменная | Описание |
|------------|----------|
| `HIGH_COST_THRESHOLD` | Порог для двойного подтверждения (default: 4000) |
| `MAX_TASKS_PER_USER_PER_HOUR` | Rate limiting (default: 20) |
| `ADMIN_IDS` | Telegram ID админов через запятую |
| `ADMIN_API_KEY` | API ключ для HTTP админ-эндпоинтов |

### 3. Сервис создания задач (task_service.py)

**Новый файл:** `bot/services/task_service.py`

Централизует логику создания задач:
- Проверка rate limiting
- Списание токенов
- Создание задачи в БД
- Постановка в очередь RQ

### 4. Репозиторий статистики (StatsRepository)

**Файл:** `bot/db/repositories.py`

Новые методы:
- `get_total_users()` — всего пользователей
- `get_total_tasks()` — всего задач
- `get_tasks_by_status()` — задачи по статусам
- `get_total_tokens_spent()` — потрачено токенов
- `get_tasks_today()` — задач сегодня
- `get_users_today()` — новых пользователей сегодня
- `get_active_users_today()` — активных сегодня
- `get_top_users()` — топ пользователей
- `get_model_usage()` — использование моделей
- `get_full_stats()` — полная статистика

### 5. Rate Limiting

**Файл:** `bot/db/repositories.py`

Новый метод `count_user_tasks_since(user_id, hours)` для подсчёта задач за период.

### 6. Админ-панель (Telegram)

**Новый файл:** `bot/handlers/admin.py`

Команды:
- `/admin` — меню с кнопками
- `/stats` — статистика
- `/addtokens <id> <amount>` — добавить токены
- `/userinfo <id>` — инфо о пользователе

### 7. Админ API (HTTP)

**Файл:** `bot/main.py`

Эндпоинты (требуют `X-Admin-API-Key`):
- `GET /admin/stats` — статистика
- `GET /admin/queue` — очередь RQ
- `GET /admin/users/{telegram_id}` — инфо о пользователе
- `POST /admin/users/{telegram_id}/tokens` — добавить токены

### 8. Обновлённые файлы

- `docker-compose.yml` — новые ENV переменные
- `.env.example` — полный пример конфигурации
- `DEVELOPER_GUIDE.md` — документация админ-панели
- `bot/handlers/__init__.py` — регистрация admin_router

### 9. Исправление gpt-image-1.5 для edit

**Файлы:**
- `bot/services/image_provider.py` — убран fallback
- `bot/handlers/edit.py` — убран fallback

Теперь `gpt-image-1.5` поддерживается для редактирования (согласно документации OpenAI).

---

## Как настроить админку

1. Узнай свой Telegram ID (напиши боту @userinfobot)

2. Добавь в `.env`:
```env
ADMIN_IDS=твой_telegram_id
ADMIN_API_KEY=сгенерируй_случайную_строку
```

3. Перезапусти бота:
```bash
docker-compose build --no-cache
docker-compose up -d
```

4. Напиши боту `/admin`
