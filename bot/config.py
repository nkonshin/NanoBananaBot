"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
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
    )


# Global config instance
config = load_config()
