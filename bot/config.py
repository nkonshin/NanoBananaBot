"""Application configuration loaded from environment variables."""

import logging
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

_logger = logging.getLogger(__name__)

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
        _logger.warning("Failed to parse integer list from value: %r", value)
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

    # BytePlus ARK (SeeDream)
    ark_api_key: str
    
    # App settings
    initial_tokens: int

    log_level: str

    telegram_request_timeout: float
    webhook_max_retries: int
    webhook_retry_delay_seconds: float
    webhook_retry_backoff: float
    disable_webhook: bool
    delete_webhook_on_shutdown: bool
    use_polling: bool  # True = polling mode (no domain needed), False = webhook mode

    webhook_secret_token: str
    use_redis_fsm_storage: bool

    # Generation settings
    high_cost_threshold: int  # Порог для двойного подтверждения
    max_tasks_per_user_per_hour: int  # Rate limiting

    # Admin settings
    admin_ids: List[int] = field(default_factory=list)  # Telegram IDs админов
    admin_api_key: str = ""  # API ключ для HTTP админ-эндпоинтов

    # Support
    support_username: str = ""  # Username поддержки (например @support)

    # Subscription settings
    subscription_channel: str = ""  # Канал для проверки подписки (@nkonshin_ai)
    subscription_required: bool = True  # Требовать подписку для новых пользователей
    
    # Welcome video
    welcome_video_file_id: str = ""  # file_id видео-кружка для приветствия
    
    # Monitoring channel
    monitoring_channel_id: str = ""  # ID приватного канала для мониторинга (например -1001234567890)
    
    # YooKassa Payment
    yookassa_shop_id: str = ""  # ID магазина ЮKassa
    yookassa_secret_key: str = ""  # Секретный ключ ЮKassa
    yookassa_return_url: str = ""  # URL возврата после оплаты

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
        ark_api_key=os.getenv("ARK_API_KEY", ""),
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
        use_polling=_parse_bool(os.getenv("USE_POLLING", "0"), default=False),

        webhook_secret_token=os.getenv("WEBHOOK_SECRET_TOKEN", ""),
        use_redis_fsm_storage=_parse_bool(os.getenv("USE_REDIS_FSM_STORAGE", "0"), default=False),

        # Generation settings
        high_cost_threshold=int(os.getenv("HIGH_COST_THRESHOLD", "20")),
        max_tasks_per_user_per_hour=int(os.getenv("MAX_TASKS_PER_USER_PER_HOUR", "20")),

        # Admin settings
        admin_ids=_parse_int_list(os.getenv("ADMIN_IDS", "")),
        admin_api_key=os.getenv("ADMIN_API_KEY", ""),

        # Support
        support_username=os.getenv("SUPPORT_USERNAME", ""),

        # Subscription settings
        subscription_channel=os.getenv("SUBSCRIPTION_CHANNEL", "@nkonshin_ai"),
        subscription_required=_parse_bool(os.getenv("SUBSCRIPTION_REQUIRED", "true"), default=True),
        
        # Welcome video
        welcome_video_file_id=os.getenv("WELCOME_VIDEO_FILE_ID", ""),
        
        # Monitoring channel
        monitoring_channel_id=os.getenv("MONITORING_CHANNEL_ID", ""),
        
        # YooKassa Payment
        yookassa_shop_id=os.getenv("YOOKASSA_SHOP_ID", ""),
        yookassa_secret_key=os.getenv("YOOKASSA_SECRET_KEY", ""),
        yookassa_return_url=os.getenv("YOOKASSA_RETURN_URL", ""),
    )


def _validate_config(cfg: Config) -> None:
    """Validate that required configuration variables are set."""
    required = {
        "bot_token": cfg.bot_token,
        "database_url": cfg.database_url,
        "openai_api_key": cfg.openai_api_key,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        env_names = ", ".join(name.upper() for name in missing)
        raise ValueError(
            f"Missing required configuration: {env_names}. "
            f"Set the corresponding environment variables."
        )


# Global config instance
config = load_config()
_validate_config(config)
