"""Admin handlers for bot management and statistics.

Commands:
- /admin - Show admin menu
- /stats - Show bot statistics
- /broadcast <message> - Send message to all users (TODO)
- /addtokens <user_id> <amount> - Add tokens to user
"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from bot.config import config
from bot.db.database import get_session_maker
from bot.db.repositories import UserRepository, StatsRepository

logger = logging.getLogger(__name__)

router = Router(name="admin")


def admin_required(func):
    """Decorator to check if user is admin."""
    async def wrapper(message: Message, *args, **kwargs):
        if not config.is_admin(message.from_user.id):
            await message.answer("❌ У вас нет доступа к этой команде.")
            return
        return await func(message, *args, **kwargs)
    return wrapper


def admin_menu_keyboard():
    """Create admin menu keyboard."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="admin:stats",
        ),
        InlineKeyboardButton(
            text="👥 Топ пользователей",
            callback_data="admin:top_users",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📈 Использование моделей",
            callback_data="admin:model_usage",
        ),
        InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data="admin:refresh",
        ),
    )
    
    return builder.as_markup()


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    """Show admin menu."""
    if not config.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    await message.answer(
        text=(
            "🔐 <b>Админ-панель</b>\n\n"
            "Выберите действие:"
        ),
        reply_markup=admin_menu_keyboard(),
    )


@router.message(Command("stats"))
async def stats_command(message: Message) -> None:
    """Show bot statistics."""
    if not config.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    await _send_stats(message)


async def _send_stats(message_or_callback) -> None:
    """Send statistics message."""
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        stats_repo = StatsRepository(session)
        stats = await stats_repo.get_full_stats()
    
    # Format status counts
    status_text = "\n".join([
        f"  • {status}: {count}"
        for status, count in stats["tasks_by_status"].items()
    ]) or "  Нет данных"
    
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"<b>Пользователи:</b>\n"
        f"  • Всего: {stats['total_users']}\n"
        f"  • Новых сегодня: {stats['users_today']}\n"
        f"  • Активных сегодня: {stats['active_users_today']}\n\n"
        f"<b>Задачи:</b>\n"
        f"  • Всего: {stats['total_tasks']}\n"
        f"  • Сегодня: {stats['tasks_today']}\n\n"
        f"<b>По статусам:</b>\n{status_text}\n\n"
        f"<b>Токены:</b>\n"
        f"  • Потрачено всего: {stats['total_tokens_spent']:,} 🪙\n\n"
        f"<i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(
            text=text,
            reply_markup=admin_menu_keyboard(),
        )
        await message_or_callback.answer("Статистика обновлена")
    else:
        await message_or_callback.answer(
            text=text,
            reply_markup=admin_menu_keyboard(),
        )


@router.callback_query(F.data == "admin:stats")
async def admin_stats_callback(callback: CallbackQuery) -> None:
    """Handle stats button click."""
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await _send_stats(callback)


@router.callback_query(F.data == "admin:refresh")
async def admin_refresh_callback(callback: CallbackQuery) -> None:
    """Handle refresh button click."""
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await _send_stats(callback)


@router.callback_query(F.data == "admin:top_users")
async def admin_top_users_callback(callback: CallbackQuery) -> None:
    """Show top users by task count."""
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        stats_repo = StatsRepository(session)
        top_users = await stats_repo.get_top_users(limit=10)
    
    if not top_users:
        text = "👥 <b>Топ пользователей</b>\n\nНет данных"
    else:
        users_text = "\n".join([
            f"{i}. {user.first_name or user.username or user.telegram_id} — {user.task_count} задач"
            for i, user in enumerate(top_users, 1)
        ])
        text = f"👥 <b>Топ 10 пользователей</b>\n\n{users_text}"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="admin:back",
        )
    )
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:model_usage")
async def admin_model_usage_callback(callback: CallbackQuery) -> None:
    """Show model usage statistics."""
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        stats_repo = StatsRepository(session)
        model_usage = await stats_repo.get_model_usage()
    
    if not model_usage:
        text = "📈 <b>Использование моделей</b>\n\nНет данных"
    else:
        total = sum(model_usage.values())
        models_text = "\n".join([
            f"  • {model}: {count} ({count * 100 // total}%)"
            for model, count in sorted(model_usage.items(), key=lambda x: -x[1])
        ])
        text = f"📈 <b>Использование моделей</b>\n\n{models_text}\n\nВсего: {total}"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="admin:back",
        )
    )
    
    await callback.message.edit_text(
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:back")
async def admin_back_callback(callback: CallbackQuery) -> None:
    """Go back to admin menu."""
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    await _send_stats(callback)


@router.message(Command("addtokens"))
async def add_tokens_command(message: Message) -> None:
    """Add tokens to a user. Usage: /addtokens <telegram_id> <amount>"""
    if not config.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    # Parse arguments
    args = message.text.split()[1:]  # Remove /addtokens
    
    if len(args) != 2:
        await message.answer(
            "❌ <b>Неверный формат</b>\n\n"
            "Использование: <code>/addtokens &lt;telegram_id&gt; &lt;amount&gt;</code>\n\n"
            "Пример: <code>/addtokens 123456789 1000</code>"
        )
        return
    
    try:
        telegram_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await message.answer("❌ telegram_id и amount должны быть числами")
        return
    
    if amount <= 0:
        await message.answer("❌ Количество токенов должно быть положительным")
        return
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        
        if user is None:
            await message.answer(f"❌ Пользователь с ID {telegram_id} не найден")
            return
        
        old_balance = user.tokens
        await user_repo.update_tokens(user.id, amount)
        new_balance = old_balance + amount
    
    await message.answer(
        f"✅ <b>Токены добавлены</b>\n\n"
        f"Пользователь: {user.first_name or user.username or telegram_id}\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"Было: {old_balance} 🪙\n"
        f"Добавлено: +{amount} 🪙\n"
        f"Стало: {new_balance} 🪙"
    )


@router.message(Command("userinfo"))
async def user_info_command(message: Message) -> None:
    """Get user info. Usage: /userinfo <telegram_id>"""
    if not config.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    args = message.text.split()[1:]
    
    if len(args) != 1:
        await message.answer(
            "❌ <b>Неверный формат</b>\n\n"
            "Использование: <code>/userinfo &lt;telegram_id&gt;</code>"
        )
        return
    
    try:
        telegram_id = int(args[0])
    except ValueError:
        await message.answer("❌ telegram_id должен быть числом")
        return
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        
        if user is None:
            await message.answer(f"❌ Пользователь с ID {telegram_id} не найден")
            return
        
        # Count user's tasks
        from bot.db.repositories import TaskRepository
        task_repo = TaskRepository(session)
        history = await task_repo.get_user_history(user.id, limit=100)
        
        done_count = sum(1 for t in history if t.status == "done")
        failed_count = sum(1 for t in history if t.status == "failed")
    
    await message.answer(
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"<b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"<b>Username:</b> @{user.username or '—'}\n"
        f"<b>Имя:</b> {user.first_name or '—'}\n"
        f"<b>Баланс:</b> {user.tokens} 🪙\n"
        f"<b>Модель:</b> {user.selected_model}\n"
        f"<b>Качество:</b> {user.image_quality}\n"
        f"<b>Размер:</b> {user.image_size}\n\n"
        f"<b>Задачи:</b>\n"
        f"  • Всего: {len(history)}\n"
        f"  • Успешных: {done_count}\n"
        f"  • Неудачных: {failed_count}\n\n"
        f"<b>Регистрация:</b> {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else '—'}"
    )
