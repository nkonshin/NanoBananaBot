"""Telegram bot handlers package."""

from aiogram import Dispatcher, Router

from bot.handlers.start import router as start_router
from bot.handlers.menu import router as menu_router
from bot.handlers.generate import router as generate_router
from bot.handlers.edit import router as edit_router
from bot.handlers.model import router as model_router
from bot.handlers.profile import router as profile_router
from bot.handlers.balance import router as balance_router
from bot.handlers.tokens import router as tokens_router
from bot.handlers.trends import router as trends_router
from bot.handlers.guide import router as guide_router
from bot.handlers.admin import router as admin_router
from bot.handlers.errors import router as errors_router


def register_all_handlers(dp: Dispatcher) -> None:
    """
    Register all handlers with the dispatcher.
    
    Order matters! More specific handlers should be registered first.
    Error handler should be registered last.
    """
    # Register routers in order of specificity
    dp.include_router(start_router)      # /start command
    dp.include_router(admin_router)      # Admin commands (/admin, /stats, etc.)
    dp.include_router(guide_router)      # /guide command and button
    dp.include_router(generate_router)   # Generation flow (FSM)
    dp.include_router(edit_router)       # Edit flow (FSM)
    dp.include_router(trends_router)     # Templates/trends (FSM)
    dp.include_router(profile_router)    # Profile callbacks
    dp.include_router(balance_router)    # /balance and /tokens commands
    dp.include_router(model_router)      # Model callbacks
    dp.include_router(tokens_router)     # Tokens callbacks
    dp.include_router(menu_router)       # Main menu navigation
    dp.include_router(errors_router)     # Global error handler (last)


__all__ = [
    "register_all_handlers",
    "start_router",
    "menu_router",
    "generate_router",
    "edit_router",
    "model_router",
    "profile_router",
    "balance_router",
    "tokens_router",
    "trends_router",
    "guide_router",
    "admin_router",
    "errors_router",
]
