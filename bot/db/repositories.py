"""Repository classes for database CRUD operations."""

from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import config
from bot.db.models import User, GenerationTask
from bot.services.image_tokens import estimate_image_tokens


class UserRepository:
    """Repository for User CRUD operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> tuple[User, bool]:
        """
        Get existing user or create a new one.
        
        Returns:
            Tuple of (user, created) where created is True if new user was created.
        """
        user = await self.get_by_telegram_id(telegram_id)
        
        if user is not None:
            return user, False
        
        default_image_tokens = estimate_image_tokens("medium", "1024x1024")

        # Create new user with initial tokens
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            tokens=config.initial_tokens * default_image_tokens,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        
        return user, True
    
    async def update_tokens(self, user_id: int, tokens_delta: int) -> Optional[User]:
        """
        Update user's token balance.
        
        Args:
            user_id: User's database ID
            tokens_delta: Amount to add (positive) or subtract (negative)
        
        Returns:
            Updated user or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            return None
        
        user.tokens += tokens_delta
        await self.session.commit()
        await self.session.refresh(user)
        
        return user
    
    async def update_model(self, user_id: int, model: str) -> Optional[User]:
        """
        Update user's selected model.
        
        Args:
            user_id: User's database ID
            model: Model name to set
        
        Returns:
            Updated user or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            return None
        
        user.selected_model = model
        await self.session.commit()
        await self.session.refresh(user)
        
        return user

    async def update_image_settings(
        self,
        user_id: int,
        image_quality: Optional[str] = None,
        image_size: Optional[str] = None,
    ) -> Optional[User]:
        """Update user's image generation settings."""

        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            return None

        if image_quality is not None:
            user.image_quality = image_quality

        if image_size is not None:
            user.image_size = image_size

        await self.session.commit()
        await self.session.refresh(user)

        return user


class TaskRepository:
    """Repository for GenerationTask CRUD operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        user_id: int,
        task_type: str,
        prompt: str,
        tokens_spent: int,
        model: str = "gpt-image-1",
        image_quality: str = "medium",
        image_size: str = "1024x1024",
        source_image_url: Optional[str] = None,
    ) -> GenerationTask:
        """
        Create a new generation task.
        
        Args:
            user_id: User's database ID
            task_type: "generate" or "edit"
            prompt: Text prompt for generation
            tokens_spent: Number of tokens spent
            source_image_url: Source image URL for edit tasks
        
        Returns:
            Created GenerationTask
        """
        task = GenerationTask(
            user_id=user_id,
            task_type=task_type,
            model=model,
            image_quality=image_quality,
            image_size=image_size,
            prompt=prompt,
            tokens_spent=tokens_spent,
            source_image_url=source_image_url,
            status="pending",
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        
        return task
    
    async def update_status(
        self,
        task_id: int,
        status: str,
        result_image_url: Optional[str] = None,
        result_file_id: Optional[str] = None,
        error_message: Optional[str] = None,
        increment_retry: bool = False,
    ) -> Optional[GenerationTask]:
        """
        Update task status and related fields.
        
        Args:
            task_id: Task's database ID
            status: New status ("pending", "processing", "done", "failed")
            result_image_url: URL of generated image (for "done" status)
            error_message: Error message (for "failed" status)
            increment_retry: Whether to increment retry count
        
        Returns:
            Updated task or None if not found
        """
        result = await self.session.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if task is None:
            return None
        
        task.status = status
        
        if result_image_url is not None:
            task.result_image_url = result_image_url

        if result_file_id is not None:
            task.result_file_id = result_file_id
        
        if error_message is not None:
            task.error_message = error_message
        
        if increment_retry:
            task.retry_count += 1
        
        await self.session.commit()
        await self.session.refresh(task)
        
        return task
    
    async def get_user_history(
        self,
        user_id: int,
        limit: int = 10,
    ) -> List[GenerationTask]:
        """
        Get user's generation history.
        
        Args:
            user_id: User's database ID
            limit: Maximum number of tasks to return (default 10)
        
        Returns:
            List of GenerationTask ordered by created_at descending
        """
        result = await self.session.execute(
            select(GenerationTask)
            .where(GenerationTask.user_id == user_id)
            .order_by(desc(GenerationTask.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_by_id(self, task_id: int) -> Optional[GenerationTask]:
        """Get task by ID."""
        result = await self.session.execute(
            select(GenerationTask).where(GenerationTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def count_user_tasks_since(
        self,
        user_id: int,
        hours: int = 1,
    ) -> int:
        """
        Count user's tasks created in the last N hours.
        Used for rate limiting.
        
        Args:
            user_id: User's database ID
            hours: Number of hours to look back
        
        Returns:
            Number of tasks created in the time period
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(func.count(GenerationTask.id))
            .where(GenerationTask.user_id == user_id)
            .where(GenerationTask.created_at >= since)
        )
        return result.scalar() or 0


class StatsRepository:
    """Repository for statistics queries."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_total_users(self) -> int:
        """Get total number of users."""
        result = await self.session.execute(
            select(func.count(User.id))
        )
        return result.scalar() or 0
    
    async def get_total_tasks(self) -> int:
        """Get total number of tasks."""
        result = await self.session.execute(
            select(func.count(GenerationTask.id))
        )
        return result.scalar() or 0
    
    async def get_tasks_by_status(self) -> dict:
        """Get task counts grouped by status."""
        result = await self.session.execute(
            select(
                GenerationTask.status,
                func.count(GenerationTask.id)
            ).group_by(GenerationTask.status)
        )
        return {row[0]: row[1] for row in result.all()}
    
    async def get_total_tokens_spent(self) -> int:
        """Get total tokens spent across all tasks."""
        result = await self.session.execute(
            select(func.sum(GenerationTask.tokens_spent))
        )
        return result.scalar() or 0
    
    async def get_tasks_today(self) -> int:
        """Get number of tasks created today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count(GenerationTask.id))
            .where(GenerationTask.created_at >= today)
        )
        return result.scalar() or 0
    
    async def get_users_today(self) -> int:
        """Get number of users registered today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count(User.id))
            .where(User.created_at >= today)
        )
        return result.scalar() or 0
    
    async def get_active_users_today(self) -> int:
        """Get number of users who created tasks today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count(func.distinct(GenerationTask.user_id)))
            .where(GenerationTask.created_at >= today)
        )
        return result.scalar() or 0
    
    async def get_top_users(self, limit: int = 10) -> List[tuple]:
        """Get top users by number of tasks."""
        result = await self.session.execute(
            select(
                User.telegram_id,
                User.username,
                User.first_name,
                func.count(GenerationTask.id).label("task_count")
            )
            .join(GenerationTask, User.id == GenerationTask.user_id)
            .group_by(User.id)
            .order_by(desc("task_count"))
            .limit(limit)
        )
        return result.all()
    
    async def get_model_usage(self) -> dict:
        """Get task counts grouped by model."""
        result = await self.session.execute(
            select(
                GenerationTask.model,
                func.count(GenerationTask.id)
            ).group_by(GenerationTask.model)
        )
        return {row[0]: row[1] for row in result.all()}
    
    async def get_full_stats(self) -> dict:
        """Get comprehensive statistics."""
        return {
            "total_users": await self.get_total_users(),
            "total_tasks": await self.get_total_tasks(),
            "tasks_by_status": await self.get_tasks_by_status(),
            "total_tokens_spent": await self.get_total_tokens_spent(),
            "tasks_today": await self.get_tasks_today(),
            "users_today": await self.get_users_today(),
            "active_users_today": await self.get_active_users_today(),
            "model_usage": await self.get_model_usage(),
        }
