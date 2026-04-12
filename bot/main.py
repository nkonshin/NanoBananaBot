"""FastAPI application with Telegram webhook and polling support.

This module provides:
- POST /webhook endpoint for Telegram updates (webhook mode)
- Long-polling for Telegram updates (polling mode, USE_POLLING=1)
- Startup: initialize database, set webhook or start polling
- Shutdown: cleanup connections
"""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Request, Response

from bot.bot import get_bot, get_dispatcher, close_bot
from bot.config import config
from bot.db.database import init_db, close_db, get_session_maker
from bot.handlers import register_all_handlers
from sqlalchemy import select, desc

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
    - Set bot commands menu
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
    
    # Set bot commands menu
    try:
        from aiogram.types import BotCommand
        
        commands = [
            BotCommand(command="start", description="🚀 Запустить бота"),
            BotCommand(command="balance", description="💰 Проверить баланс"),
            BotCommand(command="guide", description="📖 Руководство"),
            BotCommand(command="support", description="🆘 Поддержка"),
            BotCommand(command="invite", description="👥 Пригласить друга"),
        ]
        await bot.set_my_commands(commands)
        logger.info("Bot commands menu set")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")
    
    # Choose update mode: polling or webhook
    polling_task = None

    if config.use_polling:
        # Polling mode — no domain/HTTPS needed
        # Delete any existing webhook first
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Existing webhook deleted, switching to polling mode")
        except Exception as e:
            logger.warning(f"Failed to delete webhook before polling: {e}")

        # Start polling as a background task alongside FastAPI
        async def _run_polling():
            try:
                await dp.start_polling(
                    bot,
                    polling_timeout=30,  # Long-poll: Telegram holds connection up to 30s
                    handle_signals=False,  # FastAPI manages signals
                )
            except asyncio.CancelledError:
                logger.info("Polling task cancelled")
            except Exception:
                logger.exception("Polling error")

        polling_task = asyncio.create_task(_run_polling())
        logger.info("Polling started (timeout=30s, updates arrive instantly)")

    elif config.disable_webhook:
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
        logger.warning("WEBHOOK_URL not configured and USE_POLLING=0, bot will not receive updates")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop polling if running
    if polling_task is not None:
        await dp.stop_polling()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        logger.info("Polling stopped")

    # Delete webhook if in webhook mode
    if (not config.use_polling) and (not config.disable_webhook) and config.webhook_url and config.delete_webhook_on_shutdown:
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


# ============== Admin API Endpoints ==============

def verify_admin_api_key(request: Request) -> bool:
    """Verify admin API key from request headers."""
    if not config.admin_api_key:
        return False
    api_key = request.headers.get("X-Admin-API-Key")
    if not api_key:
        return False
    return secrets.compare_digest(api_key, config.admin_api_key)


@app.get("/admin/stats")
async def admin_stats(request: Request):
    """
    Get bot statistics.
    
    Requires X-Admin-API-Key header.
    """
    if not verify_admin_api_key(request):
        return Response(status_code=403, content="Forbidden")
    
    from bot.db.repositories import StatsRepository
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        stats_repo = StatsRepository(session)
        stats = await stats_repo.get_full_stats()
    
    return stats


@app.get("/admin/queue")
async def admin_queue_stats(request: Request):
    """
    Get RQ queue statistics.
    
    Requires X-Admin-API-Key header.
    """
    if not verify_admin_api_key(request):
        return Response(status_code=403, content="Forbidden")
    
    try:
        from redis import Redis
        from rq import Queue
        
        redis_conn = Redis.from_url(config.redis_url)
        queue = Queue(connection=redis_conn)
        
        return {
            "queue_name": queue.name,
            "pending_jobs": len(queue),
            "failed_jobs": queue.failed_job_registry.count,
            "finished_jobs": queue.finished_job_registry.count,
        }
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        return {"error": str(e)}


@app.get("/admin/users/{telegram_id}")
async def admin_get_user(request: Request, telegram_id: int):
    """
    Get user info by Telegram ID.
    
    Requires X-Admin-API-Key header.
    """
    if not verify_admin_api_key(request):
        return Response(status_code=403, content="Forbidden")
    
    from bot.db.repositories import UserRepository, TaskRepository
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        
        if user is None:
            return Response(status_code=404, content="User not found")
        
        task_repo = TaskRepository(session)
        history = await task_repo.get_user_history(user.id, limit=100)
        
        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "tokens": user.tokens,
            "selected_model": user.selected_model,
            "image_quality": user.image_quality,
            "image_size": user.image_size,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "tasks_count": len(history),
            "tasks_done": sum(1 for t in history if t.status == "done"),
            "tasks_failed": sum(1 for t in history if t.status == "failed"),
        }


@app.post("/admin/users/{telegram_id}/tokens")
async def admin_add_tokens(request: Request, telegram_id: int):
    """
    Add tokens to user.
    
    Requires X-Admin-API-Key header.
    Body: {"amount": 1000}
    """
    if not verify_admin_api_key(request):
        return Response(status_code=403, content="Forbidden")
    
    try:
        body = await request.json()
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        return Response(status_code=400, content="Invalid amount")
    
    if amount <= 0:
        return Response(status_code=400, content="Amount must be positive")
    
    from bot.db.repositories import UserRepository
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        
        if user is None:
            return Response(status_code=404, content="User not found")
        
        old_balance = user.tokens
        await user_repo.update_tokens(user.id, amount)
        
        return {
            "telegram_id": telegram_id,
            "old_balance": old_balance,
            "added": amount,
            "new_balance": old_balance + amount,
        }


# ============== YooKassa Webhook ==============

@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    """
    Handle YooKassa payment notifications.
    
    Events:
    - payment.succeeded - Payment completed successfully
    - payment.canceled - Payment was canceled
    - payment.waiting_for_capture - Payment is waiting for capture
    """
    try:
        data = await request.json()
        logger.info(f"YooKassa webhook received: {data.get('event')}")
        
        from bot.services.payment import PaymentService
        from bot.db.repositories import UserRepository, PaymentRepository
        from bot.keyboards.inline import SHOP_PACKAGES
        
        # Parse notification
        payment_data = PaymentService.parse_webhook_notification(data)
        
        if not payment_data:
            logger.warning("Invalid YooKassa webhook data")
            return Response(status_code=200)
        
        event = payment_data["event"]
        payment_id = payment_data["payment_id"]
        status = payment_data["status"]
        paid = payment_data["paid"]
        
        logger.info(f"YooKassa payment {payment_id}: event={event}, status={status}, paid={paid}")
        
        session_maker = get_session_maker()
        
        async with session_maker() as session:
            payment_repo = PaymentRepository(session)
            user_repo = UserRepository(session)
            
            # Find payment in database (lock row to prevent concurrent processing)
            payment = await payment_repo.get_by_yookassa_id(payment_id, for_update=True)

            if not payment:
                logger.warning(f"Payment {payment_id} not found in database")
                return Response(status_code=200)

            old_status = payment.status

            # Early exit if already processed (concurrent webhook protection)
            if old_status == status:
                logger.info(f"Payment {payment_id} already in status '{status}', skipping")
                return Response(status_code=200)
            
            # Update payment status
            payment.status = status
            payment.paid = paid
            
            # If payment succeeded and wasn't processed before
            if event == "payment.succeeded" and paid and old_status != "succeeded":
                # Check if this is a gift payment
                is_gift = payment.is_gift if hasattr(payment, 'is_gift') else False
                
                if is_gift and payment.gift_recipient_username:
                    # Handle gift payment
                    from bot.db.repositories import GiftRepository
                    gift_repo = GiftRepository(session)
                    
                    # Find the gift by recipient username and sender
                    from bot.db.models import Gift
                    result = await session.execute(
                        select(Gift)
                        .where(Gift.sender_id == payment.user_id)
                        .where(Gift.recipient_username == payment.gift_recipient_username)
                        .where(Gift.status == "pending")
                        .order_by(desc(Gift.created_at))
                        .limit(1)
                    )
                    gift = result.scalar_one_or_none()
                    
                    if gift:
                        gift.status = "paid"
                        
                        # Check if recipient already exists
                        recipient = await user_repo.get_by_username(gift.recipient_username)
                        sender = await user_repo.get_by_id(payment.user_id)
                        
                        if recipient:
                            # Recipient exists - add tokens immediately
                            await user_repo.update_tokens(recipient.id, gift.tokens_amount)
                            gift.status = "claimed"
                            gift.recipient_id = recipient.id
                            
                            # Create transaction for recipient
                            from bot.db.repositories import TransactionRepository
                            tx_repo = TransactionRepository(session)
                            sender_name = f"@{sender.username}" if sender and sender.username else "друга"
                            await tx_repo.create(
                                user_id=recipient.id,
                                type="gift_received",
                                tokens_amount=gift.tokens_amount,
                                description=f"Подарок от {sender_name}",
                                gift_id=gift.id,
                                related_user_id=sender.id if sender else None,
                            )
                            
                            logger.info(
                                f"Gift payment {payment_id} succeeded: "
                                f"{gift.tokens_amount} tokens to @{gift.recipient_username}"
                            )
                            
                            # Notify recipient
                            try:
                                bot = get_bot()
                                sender_name = f"@{sender.username}" if sender and sender.username else "друга"
                                new_balance = recipient.tokens + gift.tokens_amount
                                
                                await bot.send_message(
                                    chat_id=recipient.telegram_id,
                                    text=(
                                        f"🎁 <b>Вам подарили токены!</b>\n\n"
                                        f"<b>От:</b> {sender_name}\n"
                                        f"<b>Пакет:</b> {SHOP_PACKAGES.get(gift.package, {}).get('name', gift.package)}\n"
                                        f"<b>Токенов:</b> +{gift.tokens_amount} 🪙\n"
                                        f"<b>Ваш баланс:</b> {new_balance} 🪙\n\n"
                                        "Токены уже на вашем балансе! 🎉"
                                    ),
                                    parse_mode="HTML",
                                )
                            except Exception as e:
                                logger.error(f"Failed to notify gift recipient: {e}")
                        else:
                            logger.info(
                                f"Gift payment {payment_id} succeeded: "
                                f"{gift.tokens_amount} tokens waiting for @{gift.recipient_username}"
                            )
                        
                        # Notify sender
                        try:
                            bot = get_bot()
                            status_text = "уже получил токены! 🎉" if gift.status == "claimed" else "получит токены при входе в бота 📩"
                            
                            await bot.send_message(
                                chat_id=sender.telegram_id if sender else payment.user_id,
                                text=(
                                    f"✅ <b>Подарок оплачен!</b>\n\n"
                                    f"<b>Получатель:</b> @{gift.recipient_username}\n"
                                    f"<b>Пакет:</b> {SHOP_PACKAGES.get(gift.package, {}).get('name', gift.package)}\n"
                                    f"<b>Токенов:</b> {gift.tokens_amount} 🪙\n\n"
                                    f"<i>Статус: {status_text}</i>\n\n"
                                    "Спасибо за подарок! 💝"
                                ),
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify gift sender: {e}")
                        
                        # Notify admins
                        try:
                            from bot.services.admin_notify import notify_admins
                            await notify_admins(
                                f"🎁 <b>Новый подарок!</b>\n\n"
                                f"От: @{sender.username or '—'} ({sender.telegram_id if sender else '—'})\n"
                                f"Кому: @{gift.recipient_username}\n"
                                f"Пакет: {SHOP_PACKAGES.get(gift.package, {}).get('name', gift.package)}\n"
                                f"Сумма: {payment.amount_value} ₽\n"
                                f"Токены: {gift.tokens_amount} 🪙\n"
                                f"Статус: {'Получен' if gift.status == 'claimed' else 'Ожидает'}",
                                title="Подарок"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify admins about gift: {e}")
                else:
                    # Regular payment - add tokens to user
                    user = await user_repo.get_by_id(payment.user_id)
                    
                    if user:
                        await user_repo.update_tokens(user.id, payment.tokens_amount)
                        logger.info(
                            f"Payment {payment_id} succeeded: added {payment.tokens_amount} tokens "
                            f"to user {user.telegram_id}"
                        )
                        
                        # Create transaction record
                        from bot.db.repositories import TransactionRepository
                        tx_repo = TransactionRepository(session)
                        package_name = SHOP_PACKAGES.get(payment.package, {}).get("name", payment.package)
                        await tx_repo.create(
                            user_id=user.id,
                            type="purchase",
                            tokens_amount=payment.tokens_amount,
                            description=f"{package_name} пакет",
                            payment_id=payment.id,
                        )
                        
                        # Referral bonus: give 20% to referrer
                        if user.referrer_id:
                            referrer = await user_repo.get_by_id(user.referrer_id)
                            if referrer:
                                referral_bonus = int(payment.tokens_amount * 0.2)  # 20% bonus
                                if referral_bonus > 0:
                                    await user_repo.update_tokens(referrer.id, referral_bonus)
                                    logger.info(
                                        f"Referral bonus: added {referral_bonus} tokens "
                                        f"to referrer {referrer.telegram_id} (from user {user.telegram_id})"
                                    )
                                    
                                    # Create transaction for referrer
                                    referral_name = f"@{user.username}" if user.username else "реферала"
                                    await tx_repo.create(
                                        user_id=referrer.id,
                                        type="referral_bonus",
                                        tokens_amount=referral_bonus,
                                        description=f"Бонус от {referral_name}",
                                        related_user_id=user.id,
                                    )
                                    
                                    # Notify referrer about bonus
                                    try:
                                        bot = get_bot()
                                        new_balance = referrer.tokens + referral_bonus
                                        
                                        await bot.send_message(
                                            chat_id=referrer.telegram_id,
                                            text=(
                                                f"🎉 <b>Реферальный бонус!</b>\n\n"
                                                f"Ваш реферал {referral_name} пополнил баланс!\n\n"
                                                f"<b>Вы получили:</b> +{referral_bonus} 🪙 (20% от покупки)\n"
                                                f"<b>Ваш баланс:</b> {new_balance} 🪙\n\n"
                                                "Продолжайте приглашать друзей! 🚀"
                                            ),
                                            parse_mode="HTML",
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to notify referrer about bonus: {e}")
                        
                        # Send notification to user
                        try:
                            bot = get_bot()
                            package_name = SHOP_PACKAGES.get(payment.package, {}).get("name", payment.package)
                            new_balance = user.tokens + payment.tokens_amount
                            
                            await bot.send_message(
                                chat_id=user.telegram_id,
                                text=(
                                    "✅ <b>Оплата прошла успешно!</b>\n\n"
                                    f"<b>Пакет:</b> {package_name}\n"
                                    f"<b>Зачислено:</b> +{payment.tokens_amount} 🪙\n"
                                    f"<b>Ваш баланс:</b> {new_balance} 🪙\n\n"
                                    "Спасибо за покупку! Теперь можно творить магию 🎨"
                                ),
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            logger.error(f"Failed to send payment notification to user: {e}")
                        
                        # Notify admins
                        try:
                            from bot.services.admin_notify import notify_admins
                            await notify_admins(
                                f"💰 <b>Новая оплата!</b>\n\n"
                                f"Пользователь: @{user.username or '—'} ({user.telegram_id})\n"
                                f"Пакет: {SHOP_PACKAGES.get(payment.package, {}).get('name', payment.package)}\n"
                                f"Сумма: {payment.amount_value} ₽\n"
                                f"Токены: +{payment.tokens_amount} 🪙",
                                title="Оплата"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify admins: {e}")
            
            # If payment was canceled
            elif event == "payment.canceled" and old_status != "canceled":
                user = await user_repo.get_by_id(payment.user_id)
                
                if user:
                    logger.info(
                        f"Payment {payment_id} canceled for user {user.telegram_id}"
                    )
                    
                    # Send notification to user with shop buttons
                    try:
                        bot = get_bot()
                        from bot.keyboards.inline import tokens_keyboard
                        
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=(
                                "❌ <b>Платеж не завершен</b>\n\n"
                                "Покупка отменена, баланс остался прежним.\n\n"
                                "Если возникла ошибка — напишите нам в поддержку."
                            ),
                            reply_markup=tokens_keyboard(),
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send cancel notification to user: {e}")
            
            await session.commit()
        
        return Response(status_code=200)
        
    except Exception as e:
        payment_id_log = (
            data.get("object", {}).get("id", "unknown")
            if "data" in dir() and data
            else "unknown"
        )
        logger.exception(
            "PAYMENT_WEBHOOK_ERROR payment_id=%s error_type=%s: %s",
            payment_id_log,
            type(e).__name__,
            e,
        )
        # Return 200 to prevent YooKassa from retrying
        return Response(status_code=200)
