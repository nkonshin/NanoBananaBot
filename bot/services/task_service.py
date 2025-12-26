"""Task creation service to eliminate code duplication.

This module centralizes the logic for creating and enqueuing generation tasks,
which was previously duplicated across generate.py, edit.py, and trends.py.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from bot.db.database import get_session_maker
from bot.db.repositories import UserRepository, TaskRepository
from bot.db.models import GenerationTask
from bot.services.balance import BalanceService, InsufficientBalanceError
from bot.services.image_tokens import estimate_image_tokens

logger = logging.getLogger(__name__)


@dataclass
class TaskCreationResult:
    """Result of task creation attempt."""
    
    success: bool
    task: Optional[GenerationTask] = None
    error_type: Optional[str] = None  # "insufficient_balance", "user_not_found", "rate_limit"
    error_message: Optional[str] = None
    required_tokens: Optional[int] = None
    available_tokens: Optional[int] = None


async def calculate_task_cost(
    quality: str,
    size: str,
    multiplier: int = 1,
) -> int:
    """
    Calculate the cost of a task.
    
    Args:
        quality: Image quality (low, medium, high)
        size: Image size (1024x1024, etc.)
        multiplier: Cost multiplier (e.g., for templates)
    
    Returns:
        Total cost in tokens
    """
    return estimate_image_tokens(quality, size) * multiplier


async def create_and_enqueue_task(
    user_id: int,
    telegram_id: int,
    task_type: str,
    prompt: str,
    quality: str,
    size: str,
    model: str,
    source_image_url: Optional[str] = None,
    cost_multiplier: int = 1,
) -> TaskCreationResult:
    """
    Create a generation task and enqueue it for processing.
    
    This is the unified function for creating tasks, used by:
    - generate.py (image generation)
    - edit.py (image editing)
    - trends.py (template generation)
    
    Args:
        user_id: Database user ID
        telegram_id: Telegram user ID (for rate limiting)
        task_type: "generate" or "edit"
        prompt: Text prompt for generation
        quality: Image quality
        size: Image size
        model: Model name
        source_image_url: Source image for edit tasks (file_id or URL)
        cost_multiplier: Multiplier for cost (e.g., template cost)
    
    Returns:
        TaskCreationResult with success status and task or error info
    """
    cost = await calculate_task_cost(quality, size, cost_multiplier)
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        balance_service = BalanceService(session)
        task_repo = TaskRepository(session)
        user_repo = UserRepository(session)
        
        # Verify user exists
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return TaskCreationResult(
                success=False,
                error_type="user_not_found",
                error_message="Пользователь не найден",
            )
        
        # Check rate limiting
        from bot.config import config
        recent_tasks = await task_repo.count_user_tasks_since(
            user_id=user_id,
            hours=1,
        )
        if recent_tasks >= config.max_tasks_per_user_per_hour:
            return TaskCreationResult(
                success=False,
                error_type="rate_limit",
                error_message=f"Превышен лимит: {config.max_tasks_per_user_per_hour} задач в час",
            )
        
        try:
            # Deduct tokens
            await balance_service.deduct_tokens(user_id, cost)
            
            # Create task
            task = await task_repo.create(
                user_id=user_id,
                task_type=task_type,
                prompt=prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
                source_image_url=source_image_url,
            )
            
            logger.info(f"Created {task_type} task {task.id} for user {user_id}")
            
        except InsufficientBalanceError as e:
            return TaskCreationResult(
                success=False,
                error_type="insufficient_balance",
                error_message="Недостаточно токенов",
                required_tokens=e.required,
                available_tokens=e.available,
            )
    
    # Enqueue task to RQ (outside of DB session)
    try:
        from bot.tasks.generation import enqueue_generation_task
        enqueue_generation_task(task.id)
    except Exception as e:
        logger.error(f"Failed to enqueue task {task.id}: {e}")
        # Task is created, worker will pick it up eventually
    
    return TaskCreationResult(
        success=True,
        task=task,
    )


def build_insufficient_balance_text(required: int, available: int) -> str:
    """Build error message for insufficient balance."""
    return (
        f"❌ <b>Недостаточно токенов</b>\n\n"
        f"Требуется: {required} 🪙\n"
        f"Ваш баланс: {available} 🪙\n\n"
        "Пополните баланс в разделе «Купить токены»"
    )


def build_rate_limit_text(limit: int) -> str:
    """Build error message for rate limit."""
    return (
        f"⚠️ <b>Превышен лимит запросов</b>\n\n"
        f"Максимум {limit} генераций в час.\n"
        "Попробуйте позже."
    )


def build_task_created_text(task_id: int, task_type: str) -> str:
    """Build success message for task creation."""
    action = "генерируется" if task_type == "generate" else "редактируется"
    return (
        "✅ <b>Задача создана!</b>\n\n"
        f"🆔 ID задачи: <code>{task_id}</code>\n\n"
        f"⏳ Ваше изображение {action}...\n"
        "Я отправлю результат, когда будет готово.\n\n"
        "Это может занять 10-30 секунд."
    )
