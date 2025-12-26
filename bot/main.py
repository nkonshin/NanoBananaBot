"""FastAPI application with Telegram webhook integration.

This module provides:
- POST /webhook endpoint for Telegram updates
- Startup: set webhook, initialize database
- Shutdown: delete webhook, close connections
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Request, Response

from bot.bot import get_bot, get_dispatcher, close_bot
from bot.config import config
from bot.db.database import init_db, close_db
from bot.handlers import register_all_handlers

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Startup:
    - Initialize database
    - Register handlers
    - Set Telegram webhook
    
    Shutdown:
    - Delete Telegram webhook
    - Close bot session
    - Close database connections
    """
    # Startup
    logger.info("Starting application...")
    
    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Get bot and dispatcher
    bot = get_bot()
    dp = get_dispatcher()
    
    # Register all handlers
    register_all_handlers(dp)
    logger.info("Handlers registered")
    
    # Set webhook
    if config.disable_webhook:
        logger.warning("Webhook disabled by DISABLE_WEBHOOK=1")
    elif config.webhook_url:
        webhook_url = f"{config.webhook_url}/webhook"

        delay = max(config.webhook_retry_delay_seconds, 0.1)
        for attempt in range(1, max(config.webhook_max_retries, 1) + 1):
            try:
                secret_token = config.webhook_secret_token or None
                await bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True,
                    request_timeout=config.telegram_request_timeout,
                    secret_token=secret_token,
                )
                logger.info(f"Webhook set to: {webhook_url}")
                break
            except Exception:
                logger.exception(
                    "Failed to set webhook (attempt %s/%s)",
                    attempt,
                    config.webhook_max_retries,
                )
                if attempt >= config.webhook_max_retries:
                    logger.error(
                        "Webhook was not set after %s attempts; continuing startup.",
                        config.webhook_max_retries,
                    )
                    break
                await asyncio.sleep(delay)
                delay *= max(config.webhook_retry_backoff, 1.0)
    else:
        logger.warning("WEBHOOK_URL not configured, webhook not set")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Delete webhook
    if (not config.disable_webhook) and config.webhook_url and config.delete_webhook_on_shutdown:
        try:
            await bot.delete_webhook(request_timeout=config.telegram_request_timeout)
            logger.info("Webhook deleted")
        except Exception as e:
            logger.error(f"Failed to delete webhook: {e}")
    
    # Close bot session
    await close_bot()
    logger.info("Bot session closed")
    
    # Close database connections
    await close_db()
    logger.info("Database connections closed")


# Create FastAPI application
app = FastAPI(
    title="Telegram AI Image Bot",
    description="AI-powered image generation bot for Telegram",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """
    Handle incoming Telegram updates via webhook.
    
    Receives updates from Telegram and processes them through aiogram dispatcher.
    """
    try:
        if config.webhook_secret_token:
            request_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if request_secret != config.webhook_secret_token:
                logger.warning("Webhook request rejected: invalid secret token")
                return Response(status_code=403)

        # Parse update from request body
        update_data = await request.json()
        update = Update.model_validate(update_data)
        
        # Get bot and dispatcher
        bot = get_bot()
        dp = get_dispatcher()
        
        # Process update
        await dp.feed_update(bot=bot, update=update)
        
        return Response(status_code=200)
    
    except Exception:
        logger.exception("Error processing webhook update")
        # Return 200 to prevent Telegram from retrying
        return Response(status_code=200)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Telegram AI Image Bot",
        "version": "1.0.0",
        "status": "running",
    }
