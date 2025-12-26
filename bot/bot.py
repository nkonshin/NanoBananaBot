"""Aiogram Bot and Dispatcher initialization."""

import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import config

logger = logging.getLogger(__name__)

# Bot instance - initialized lazily
_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None


def get_bot() -> Bot:
    """Get or create the Bot instance."""
    global _bot
    if _bot is None:
        if not config.bot_token:
            raise ValueError("BOT_TOKEN is not configured")
        _bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        logger.info("Bot instance created")
    return _bot


def get_dispatcher() -> Dispatcher:
    """Get or create the Dispatcher instance with FSM storage."""
    global _dp
    if _dp is None:
        if config.use_redis_fsm_storage:
            from aiogram.fsm.storage.redis import RedisStorage

            storage = RedisStorage.from_url(config.redis_url)
            _dp = Dispatcher(storage=storage)
            logger.info("Dispatcher created with RedisStorage")
        else:
            storage = MemoryStorage()
            _dp = Dispatcher(storage=storage)
            logger.info("Dispatcher created with MemoryStorage")
    return _dp


async def close_bot() -> None:
    """Close bot session."""
    global _bot
    if _bot is not None:
        await _bot.session.close()
        _bot = None
        logger.info("Bot session closed")
