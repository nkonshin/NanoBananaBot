"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_int_list(value: str) -> List[int]:
    """Parse comma-separated list of integers (Telegram IDs)."""
    if not value:
        return []
    try:
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError:
        return []


@dataclass
class Config:
    """Application configuration."""
    
    # Telegram Bot
    bot_token: str
    webhook_url: str
    
    # Database
    database_url: str
    
    # Redis
    redis_url: str
    
    # OpenAI
    openai_api_key: str
    
    # App settings
    initial_tokens: int

    log_level: str

    telegram_request_timeout: float
    webhook_max_retries: int
    webhook_retry_delay_seconds: float
    webhook_retry_backoff: float
    disable_webhook: bool
    delete_webhook_on_shutdown: bool

    webhook_secret_token: str
    use_redis_fsm_storage: bool

    # Generation settings
    high_cost_threshold: int  # Порог для двойного подтверждения
    max_tasks_per_user_per_hour: int  # Rate limiting

    # Admin settings
    admin_ids: List[int] = field(default_factory=list)  # Telegram IDs админов
    admin_api_key: str = ""  # API ключ для HTTP админ-эндпоинтов

    def is_admin(self, telegram_id: int) -> bool:
        """Check if user is admin."""
        return telegram_id in self.admin_ids


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        bot_token=os.getenv("BOT_TOKEN", ""),
        webhook_url=os.getenv("WEBHOOK_URL", ""),
        database_url=os.getenv("DATABASE_URL", ""),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        initial_tokens=int(os.getenv("INITIAL_TOKENS", "10")),

        log_level=os.getenv("LOG_LEVEL", "INFO"),

        telegram_request_timeout=float(os.getenv("TELEGRAM_REQUEST_TIMEOUT", "60")),
        webhook_max_retries=int(os.getenv("WEBHOOK_MAX_RETRIES", "5")),
        webhook_retry_delay_seconds=float(os.getenv("WEBHOOK_RETRY_DELAY_SECONDS", "2")),
        webhook_retry_backoff=float(os.getenv("WEBHOOK_RETRY_BACKOFF", "2")),
        disable_webhook=_parse_bool(os.getenv("DISABLE_WEBHOOK", "0"), default=False),
        delete_webhook_on_shutdown=_parse_bool(
            os.getenv("DELETE_WEBHOOK_ON_SHUTDOWN", "1"), default=True
        ),

        webhook_secret_token=os.getenv("WEBHOOK_SECRET_TOKEN", ""),
        use_redis_fsm_storage=_parse_bool(os.getenv("USE_REDIS_FSM_STORAGE", "0"), default=False),

        # Generation settings
        high_cost_threshold=int(os.getenv("HIGH_COST_THRESHOLD", "4000")),
        max_tasks_per_user_per_hour=int(os.getenv("MAX_TASKS_PER_USER_PER_HOUR", "20")),

        # Admin settings
        admin_ids=_parse_int_list(os.getenv("ADMIN_IDS", "")),
        admin_api_key=os.getenv("ADMIN_API_KEY", ""),
    )


# Global config instance
config = load_config()
