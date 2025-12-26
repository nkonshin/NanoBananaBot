# 🛠️ Developer Guide — NanoBananaBot

Подробное руководство по архитектуре и коду проекта для разработчиков.

---

## 📁 Структура проекта

```
NanoBananaBot/
├── bot/                      # Основной код бота
│   ├── __init__.py
│   ├── main.py               # Точка входа FastAPI приложения
│   ├── bot.py                # Создание экземпляра бота и диспетчера
│   ├── config.py             # Конфигурация из переменных окружения
│   ├── db/                   # Работа с базой данных
│   │   ├── database.py       # Подключение к PostgreSQL
│   │   ├── models.py         # SQLAlchemy модели (таблицы)
│   │   └── repositories.py   # CRUD операции с БД
│   ├── handlers/             # Обработчики сообщений и callback'ов
│   │   ├── start.py          # Команда /start
│   │   ├── menu.py           # Главное меню и навигация
│   │   ├── generate.py       # Генерация изображений
│   │   ├── edit.py           # Редактирование изображений
│   │   ├── model.py          # Выбор модели AI
│   │   ├── profile.py        # Личный кабинет
│   │   └── templates.py      # Готовые шаблоны промптов
│   ├── keyboards/            # Клавиатуры
│   │   └── inline.py         # Inline-кнопки
│   ├── services/             # Бизнес-логика
│   │   ├── image_provider.py # Работа с OpenAI Images API
│   │   └── balance.py        # Управление токенами
│   ├── states/               # FSM состояния
│   │   └── generation.py     # Состояния для генерации/редактирования
│   ├── tasks/                # Фоновые задачи
│   │   └── generation.py     # RQ задачи генерации
│   ├── templates/            # Шаблоны промптов
│   │   └── prompts.py        # Готовые промпты
│   └── utils/                # Утилиты
│       └── helpers.py        # Вспомогательные функции
├── alembic/                  # Миграции базы данных
├── tests/                    # Тесты
├── worker.py                 # RQ воркер для фоновых задач
├── docker-compose.yml        # Docker конфигурация
├── Dockerfile                # Образ приложения
└── requirements.txt          # Python зависимости
```

---

## 🔄 Как работает бот (поток данных)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Telegram   │────▶│   nginx     │────▶│  FastAPI    │
│   Server    │     │  (reverse   │     │  (webhook)  │
└─────────────┘     │   proxy)    │     └──────┬──────┘
                    └─────────────┘            │
                                               ▼
                                    ┌─────────────────┐
                                    │    aiogram      │
                                    │  (dispatcher)   │
                                    └────────┬────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
            ┌───────────┐           ┌───────────────┐         ┌───────────┐
            │ handlers/ │           │   services/   │         │    db/    │
            │  (логика  │           │ (бизнес-      │         │ (данные)  │
            │  команд)  │           │  логика)      │         │           │
            └─────┬─────┘           └───────┬───────┘         └─────┬─────┘
                  │                         │                       │
                  │                         ▼                       ▼
                  │                 ┌───────────────┐       ┌───────────────┐
                  │                 │     Redis     │       │  PostgreSQL   │
                  │                 │   (очередь)   │       │    (БД)       │
                  │                 └───────┬───────┘       └───────────────┘
                  │                         │
                  │                         ▼
                  │                 ┌───────────────┐
                  │                 │  RQ Worker    │
                  │                 │ (фоновые      │
                  │                 │  задачи)      │
                  │                 └───────┬───────┘
                  │                         │
                  │                         ▼
                  │                 ┌───────────────┐
                  │                 │  OpenAI API   │
                  │                 │ (генерация)   │
                  │                 └───────┬───────┘
                  │                         │
                  ▼                         ▼
            ┌─────────────────────────────────────┐
            │         Ответ пользователю          │
            └─────────────────────────────────────┘
```

---

## 📦 Ключевые компоненты

### 1. `bot/main.py` — Точка входа

```python
# FastAPI приложение с webhook endpoint
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """Принимает обновления от Telegram."""
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return Response()
```

**Что происходит:**
1. Telegram отправляет POST запрос на `/webhook`
2. FastAPI принимает JSON с обновлением
3. aiogram парсит обновление и передаёт в диспетчер
4. Диспетчер находит нужный handler и вызывает его

**Почему webhook, а не polling:**
- Polling — бот сам опрашивает Telegram каждые N секунд (простой, но неэффективный)
- Webhook — Telegram сам отправляет обновления (эффективнее, нужен HTTPS)

---

### 2. `bot/bot.py` — Создание бота

```python
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
```

**Компоненты:**
- `Bot` — экземпляр бота для отправки сообщений
- `Dispatcher` — маршрутизатор, направляет обновления в handlers
- `MemoryStorage` — хранилище FSM состояний в памяти

**parse_mode="HTML"** — позволяет использовать HTML теги в сообщениях:
```python
await message.answer("<b>Жирный</b> и <i>курсив</i>")
```

---

### 3. `bot/config.py` — Конфигурация

```python
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    bot_token: str
    database_url: str
    redis_url: str
    openai_api_key: str
    webhook_url: str
    initial_tokens: int = 10
    
    class Config:
        env_file = ".env"

config = Config()
```

**Pydantic Settings:**
- Автоматически читает переменные из `.env`
- Валидирует типы (если `bot_token` не строка — ошибка)
- Значения по умолчанию (`initial_tokens = 10`)

---

## 🗄️ База данных (`bot/db/`)

### `database.py` — Подключение

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(config.database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
```

**Почему async:**
- Бот обрабатывает много запросов одновременно
- Синхронные запросы к БД блокировали бы весь event loop
- `asyncpg` — асинхронный драйвер PostgreSQL

### `models.py` — Модели (таблицы)

```python
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=10)
    selected_model: Mapped[str] = mapped_column(String(50), default="gpt-image-1")
    
    # Связь с задачами
    tasks: Mapped[List["GenerationTask"]] = relationship("GenerationTask", back_populates="user")
```

**SQLAlchemy ORM:**
- `Mapped[int]` — типизация для IDE
- `mapped_column()` — определение колонки
- `relationship()` — связь между таблицами (один User → много Tasks)
- `BigInteger` — для telegram_id (может быть > 2 млрд)

### `repositories.py` — CRUD операции

```python
class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, telegram_id: int, username: str = None) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            return user, False  # Существующий
        
        user = User(telegram_id=telegram_id, username=username, tokens=config.initial_tokens)
        self.session.add(user)
        await self.session.commit()
        return user, True  # Новый
```

**Паттерн Repository:**
- Изолирует логику работы с БД
- Handler не знает про SQL — только вызывает методы репозитория
- Легко тестировать (можно подменить репозиторий на mock)

---

## 🎮 Handlers (`bot/handlers/`)

### Как работают handlers

```python
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

router = Router(name="start")

# Handler для команды /start
@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer("Привет!", reply_markup=main_menu_keyboard())

# Handler для callback кнопки
@router.callback_query(F.data == "menu:generate")
async def menu_generate(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Опишите картинку:")
    await callback.answer()  # Убирает "часики" на кнопке
```

**Router** — группирует связанные handlers:
```python
# В main.py
dp.include_router(start.router)
dp.include_router(menu.router)
dp.include_router(generate.router)
```

**Фильтры:**
- `Command("start")` — команда /start
- `F.data == "menu:generate"` — callback с определённым data
- `F.photo` — сообщение с фото
- `StateFilter(GenerationStates.waiting_prompt)` — определённое FSM состояние

### `generate.py` — Генерация изображений

```python
@router.message(GenerationStates.waiting_prompt, F.text)
async def process_prompt(message: Message, state: FSMContext) -> None:
    prompt = message.text
    user_tg = message.from_user
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        task_repo = TaskRepository(session)
        balance_service = BalanceService(session)
        
        # Получаем пользователя
        user = await user_repo.get_by_telegram_id(user_tg.id)
        
        # Проверяем баланс
        if not await balance_service.check_balance(user.id, tokens_cost=1):
            await message.answer("Недостаточно токенов!")
            return
        
        # Списываем токены
        await balance_service.deduct_tokens(user.id, tokens_cost=1)
        
        # Создаём задачу в БД
        task = await task_repo.create(
            user_id=user.id,
            task_type="generate",
            prompt=prompt,
            tokens_spent=1,
        )
        
        # Ставим в очередь
        enqueue_generation_task(task.id)
    
    await message.answer("⏳ Генерирую изображение...")
    await state.clear()
```

**Поток:**
1. Пользователь в состоянии `waiting_prompt` отправляет текст
2. Проверяем баланс токенов
3. Списываем токены
4. Создаём запись задачи в БД
5. Ставим задачу в очередь Redis
6. Отвечаем пользователю "Генерирую..."
7. Очищаем FSM состояние

---

## 🔀 FSM — Finite State Machine (`bot/states/`)

FSM позволяет вести "диалог" с пользователем:

```python
from aiogram.fsm.state import State, StatesGroup

class GenerationStates(StatesGroup):
    waiting_prompt = State()      # Ждём текст промпта
    waiting_confirmation = State() # Ждём подтверждения

class EditStates(StatesGroup):
    waiting_image = State()       # Ждём фото
    waiting_prompt = State()      # Ждём описание изменений
```

**Использование:**

```python
# Устанавливаем состояние
@router.callback_query(F.data == "menu:generate")
async def menu_generate(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GenerationStates.waiting_prompt)
    await callback.message.edit_text("Опишите картинку:")

# Обрабатываем в этом состоянии
@router.message(GenerationStates.waiting_prompt, F.text)
async def process_prompt(message: Message, state: FSMContext) -> None:
    prompt = message.text
    # ... обработка ...
    await state.clear()  # Сбрасываем состояние

# Сохраняем данные между состояниями
await state.update_data(image_file_id=photo.file_id)
data = await state.get_data()
file_id = data["image_file_id"]
```

**Зачем FSM:**
- Без FSM бот не знает, что пользователь хочет сделать
- FSM запоминает контекст диалога
- Можно передавать данные между шагами

---

## ⌨️ Клавиатуры (`bot/keyboards/`)

### Inline клавиатуры

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Первый ряд — 2 кнопки
    builder.row(
        InlineKeyboardButton(text="🎨 Создать", callback_data="menu:generate"),
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="menu:edit"),
    )
    # Второй ряд — 2 кнопки
    builder.row(
        InlineKeyboardButton(text="🤖 Модель", callback_data="menu:model"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
    )
    
    return builder.as_markup()
```

**callback_data:**
- Строка до 64 байт
- Передаётся в handler при нажатии
- Формат `prefix:action` для удобства фильтрации

---

## 🖼️ Сервисы (`bot/services/`)

### `image_provider.py` — OpenAI Images API

```python
class OpenAIImageProvider:
    def __init__(self, api_key: str, model: str = "gpt-image-1"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def generate(self, prompt: str) -> GenerationResult:
        response = await self.client.images.generate(
            model=self.model,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        
        # GPT Image модели возвращают base64
        image_data = response.data[0]
        if image_data.b64_json:
            return GenerationResult(success=True, image_base64=image_data.b64_json)
        
        return GenerationResult(success=False, error="No image returned")
    
    async def edit(self, image_source: str, prompt: str, bot_token: str) -> GenerationResult:
        # Скачиваем изображение из Telegram
        bot = Bot(token=bot_token)
        file = await bot.get_file(image_source)
        
        file_buffer = io.BytesIO()
        await bot.download_file(file.file_path, file_buffer)
        
        # Отправляем в OpenAI
        response = await self.client.images.edit(
            model="gpt-image-1",  # gpt-image-1.5 не поддерживает edit
            image=file_buffer,
            prompt=prompt,
        )
        
        return GenerationResult(success=True, image_base64=response.data[0].b64_json)
```

**Особенности OpenAI Images API:**
- `gpt-image-1`, `gpt-image-1.5` — всегда возвращают base64
- `dall-e-2`, `dall-e-3` — могут возвращать URL
- Edit endpoint поддерживает только `gpt-image-1` и `dall-e-2`

### `balance.py` — Управление токенами

```python
class BalanceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
    
    async def check_balance(self, user_id: int, tokens_cost: int) -> bool:
        user = await self.user_repo.get_by_id(user_id)
        return user.tokens >= tokens_cost
    
    async def deduct_tokens(self, user_id: int, tokens_cost: int) -> None:
        await self.user_repo.update_tokens(user_id, -tokens_cost)
    
    async def refund_task(self, task_id: int) -> None:
        """Возврат токенов при ошибке генерации."""
        task = await self.task_repo.get_by_id(task_id)
        await self.user_repo.update_tokens(task.user_id, task.tokens_spent)
```

---

## ⚙️ Фоновые задачи (`bot/tasks/`)

### Зачем нужны фоновые задачи

Генерация изображения занимает 10-40 секунд. Если делать это в handler:
- Telegram ждёт ответ максимум 60 секунд
- Блокируется обработка других пользователей
- При ошибке сложно повторить

**Решение — очередь задач:**
1. Handler создаёт задачу и сразу отвечает "Генерирую..."
2. Задача уходит в Redis очередь
3. Отдельный worker берёт задачу и выполняет
4. Worker отправляет результат пользователю

### `generation.py` — RQ задачи

```python
from redis import Redis
from rq import Queue, Retry

def get_queue() -> Queue:
    redis_conn = Redis.from_url(config.redis_url)
    return Queue(connection=redis_conn)

def enqueue_generation_task(task_id: int) -> None:
    queue = get_queue()
    queue.enqueue(
        process_generation_task,
        task_id,
        retry=Retry(max=3, interval=[10, 30, 60]),  # 3 попытки с задержкой
    )

def process_generation_task(task_id: int) -> bool:
    """Выполняется в worker процессе."""
    # Синхронный контекст — запускаем async код
    return asyncio.get_event_loop().run_until_complete(
        _process_generation_task_async(task_id)
    )

async def _process_generation_task_async(task_id: int) -> bool:
    # 1. Обновляем статус на "processing"
    await task_repo.update_status(task_id, status="processing")
    
    # 2. Генерируем изображение
    result = await image_provider.generate(prompt)
    
    if result.success:
        # 3. Обновляем статус на "done"
        await task_repo.update_status(task_id, status="done")
        
        # 4. Отправляем результат пользователю
        await _send_result_to_user(task, result.image_base64)
        return True
    else:
        # 5. При ошибке — retry или refund
        if retry_count >= MAX_RETRIES:
            await balance_service.refund_task(task_id)
        raise GenerationError(result.error)
```

### `worker.py` — RQ воркер

```python
from rq import Worker, Queue
from redis import Redis

redis_conn = Redis.from_url(config.redis_url)
queue = Queue(connection=redis_conn)

if __name__ == "__main__":
    worker = Worker([queue], connection=redis_conn)
    worker.work()
```

**Запуск:** `python worker.py`

Worker — отдельный процесс, который:
1. Слушает Redis очередь
2. Берёт задачи по одной
3. Выполняет функцию `process_generation_task`
4. При ошибке — повторяет или помечает как failed

---

## 🐳 Docker

### `Dockerfile`

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .
```

**Multi-stage build:**
- `builder` — устанавливает зависимости
- Финальный образ — копирует только установленные пакеты
- Результат меньше по размеру

### `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
  
  app:
    build: .
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
    command: uvicorn bot.main:app --host 0.0.0.0 --port 8000
  
  worker:
    build: .
    command: python worker.py
```

**Сеть Docker:**
- Контейнеры видят друг друга по имени сервиса
- `postgres:5432` — не localhost, а имя контейнера
- `redis:6379` — аналогично

---

## 🧪 Тестирование

### `tests/conftest.py` — Фикстуры

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest.fixture
async def db_session():
    """Создаёт тестовую БД в памяти."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine)
    async with async_session() as session:
        yield session
```

### `tests/test_services.py`

```python
@pytest.mark.asyncio
async def test_deduct_tokens(db_session):
    user_repo = UserRepository(db_session)
    balance_service = BalanceService(db_session)
    
    user, _ = await user_repo.get_or_create(telegram_id=123)
    initial_tokens = user.tokens
    
    await balance_service.deduct_tokens(user.id, 5)
    
    updated_user = await user_repo.get_by_telegram_id(123)
    assert updated_user.tokens == initial_tokens - 5
```

**Запуск:** `pytest tests/ -v`

---

## 🔧 Alembic — Миграции БД

### Создание миграции

```bash
alembic revision --autogenerate -m "Add selected_model to users"
```

Alembic сравнивает модели с БД и генерирует миграцию:

```python
# alembic/versions/xxx_add_selected_model.py
def upgrade():
    op.add_column('users', sa.Column('selected_model', sa.String(50), default='gpt-image-1'))

def downgrade():
    op.drop_column('users', 'selected_model')
```

### Применение миграций

```bash
alembic upgrade head  # Применить все
alembic downgrade -1  # Откатить последнюю
```

---

## 📝 Полезные паттерны

### Dependency Injection через контекст

```python
async with session_maker() as session:
    user_repo = UserRepository(session)
    balance_service = BalanceService(session)
    # Все операции в одной транзакции
```

### Graceful error handling

```python
try:
    result = await image_provider.generate(prompt)
except Exception as e:
    logger.error(f"Generation failed: {e}")
    await balance_service.refund_task(task_id)
    await notify_user_about_error(user_id)
```

### Callback data conventions

```python
# Формат: prefix:action или prefix:action:id
"menu:generate"      # Действие в меню
"model:gpt-image-1"  # Выбор модели
"history:show:123"   # Показать задачу с ID 123
```

---

## 🚀 Что можно улучшить

1. **Кэширование** — Redis для часто запрашиваемых данных
2. **Rate limiting** — ограничение запросов от одного пользователя
3. **Мониторинг** — Prometheus + Grafana для метрик
4. **Логирование** — структурированные логи в JSON
5. **CI/CD** — автоматический деплой при push в main

---

Если есть вопросы по конкретным частям кода — спрашивай! 🙌

## 🔐 Админ-панель

### Telegram команды для админов

Админы определяются через переменную окружения `ADMIN_IDS` (список Telegram ID через запятую).

**Доступные команды:**

| Команда | Описание |
|---------|----------|
| `/admin` | Открыть админ-меню с кнопками |
| `/stats` | Показать статистику бота |
| `/addtokens <telegram_id> <amount>` | Добавить токены пользователю |
| `/userinfo <telegram_id>` | Информация о пользователе |

**Пример использования:**
```
/addtokens 123456789 5000
/userinfo 123456789
```

### HTTP API для админов

Все эндпоинты требуют заголовок `X-Admin-API-Key` с ключом из `ADMIN_API_KEY`.

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/admin/stats` | Полная статистика бота |
| GET | `/admin/queue` | Статистика очереди RQ |
| GET | `/admin/users/{telegram_id}` | Информация о пользователе |
| POST | `/admin/users/{telegram_id}/tokens` | Добавить токены |

**Примеры запросов:**

```bash
# Получить статистику
curl -H "X-Admin-API-Key: your_key" https://your-domain.com/admin/stats

# Добавить токены пользователю
curl -X POST \
  -H "X-Admin-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{"amount": 1000}' \
  https://your-domain.com/admin/users/123456789/tokens
```

---

## ⚙️ Новые переменные окружения

### Настройки генерации

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HIGH_COST_THRESHOLD` | 4000 | Порог токенов для двойного подтверждения |
| `MAX_TASKS_PER_USER_PER_HOUR` | 20 | Лимит задач на пользователя в час |

### Настройки админки

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `ADMIN_IDS` | (пусто) | Telegram ID админов через запятую |
| `ADMIN_API_KEY` | (пусто) | API ключ для HTTP эндпоинтов |

**Пример .env:**
```env
# Админы (твой Telegram ID)
ADMIN_IDS=123456789

# Ключ для HTTP API (сгенерируй случайную строку)
ADMIN_API_KEY=super_secret_key_12345

# Лимиты
HIGH_COST_THRESHOLD=4000
MAX_TASKS_PER_USER_PER_HOUR=20
```

---

## 📊 Статистика

Админ-панель показывает:

- **Пользователи:** всего, новых сегодня, активных сегодня
- **Задачи:** всего, сегодня, по статусам (pending/processing/done/failed)
- **Токены:** всего потрачено
- **Топ пользователей:** по количеству задач
- **Использование моделей:** gpt-image-1 vs gpt-image-1.5

---

## 🛡️ Rate Limiting

Защита от спама реализована через `MAX_TASKS_PER_USER_PER_HOUR`:

- Подсчитывается количество задач пользователя за последний час
- При превышении лимита возвращается ошибка
- Лимит настраивается через переменную окружения

---

## 🔧 Сервис создания задач

Для устранения дублирования кода создан `bot/services/task_service.py`:

```python
from bot.services.task_service import create_and_enqueue_task, TaskCreationResult

result = await create_and_enqueue_task(
    user_id=user.id,
    telegram_id=user.telegram_id,
    task_type="generate",  # или "edit"
    prompt="A cute cat",
    quality="medium",
    size="1024x1024",
    model="gpt-image-1",
)

if result.success:
    task = result.task
else:
    # result.error_type: "insufficient_balance", "user_not_found", "rate_limit"
    # result.error_message: текст ошибки
```

---
