"""Tests for database models and repositories."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User, GenerationTask, Template
from bot.db.repositories import UserRepository, TaskRepository


class TestUserModel:
    """Tests for User model."""

    @pytest.mark.asyncio
    async def test_create_user(self, test_session: AsyncSession):
        """Test creating a user with default values."""
        user = User(
            telegram_id=123456789,
            username="testuser",
            first_name="Test",
            tokens=10,
        )
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        assert user.id is not None
        assert user.telegram_id == 123456789
        assert user.username == "testuser"
        assert user.tokens == 10
        assert user.selected_model == "gpt-image-1"
        assert user.created_at is not None


class TestGenerationTaskModel:
    """Tests for GenerationTask model."""

    @pytest.mark.asyncio
    async def test_create_task(self, test_session: AsyncSession):
        """Test creating a generation task."""
        user = User(telegram_id=123456789, tokens=10)
        test_session.add(user)
        await test_session.commit()

        task = GenerationTask(
            user_id=user.id,
            task_type="generate",
            prompt="A beautiful sunset",
            tokens_spent=1,
        )
        test_session.add(task)
        await test_session.commit()
        await test_session.refresh(task)

        assert task.id is not None
        assert task.user_id == user.id
        assert task.task_type == "generate"
        assert task.status == "pending"
        assert task.retry_count == 0


class TestUserRepository:
    """Tests for UserRepository."""

    @pytest.mark.asyncio
    async def test_get_or_create_new_user(self, test_session: AsyncSession):
        """Test creating a new user via get_or_create."""
        repo = UserRepository(test_session)
        user, created = await repo.get_or_create(
            telegram_id=111222333,
            username="newuser",
            first_name="New",
        )

        assert created is True
        assert user.telegram_id == 111222333
        assert user.username == "newuser"
        assert user.tokens == 10  # Default initial tokens

    @pytest.mark.asyncio
    async def test_get_or_create_existing_user(self, test_session: AsyncSession):
        """Test getting existing user via get_or_create."""
        repo = UserRepository(test_session)
        
        # Create user first
        user1, created1 = await repo.get_or_create(telegram_id=444555666)
        assert created1 is True
        
        # Try to get_or_create again
        user2, created2 = await repo.get_or_create(telegram_id=444555666)
        assert created2 is False
        assert user1.id == user2.id

    @pytest.mark.asyncio
    async def test_update_tokens(self, test_session: AsyncSession):
        """Test updating user tokens."""
        repo = UserRepository(test_session)
        user, _ = await repo.get_or_create(telegram_id=777888999)
        initial_tokens = user.tokens

        updated_user = await repo.update_tokens(user.id, -5)
        assert updated_user.tokens == initial_tokens - 5


class TestTaskRepository:
    """Tests for TaskRepository."""

    @pytest.mark.asyncio
    async def test_create_task(self, test_session: AsyncSession):
        """Test creating a generation task."""
        user_repo = UserRepository(test_session)
        task_repo = TaskRepository(test_session)

        user, _ = await user_repo.get_or_create(telegram_id=123123123)
        task = await task_repo.create(
            user_id=user.id,
            task_type="generate",
            prompt="Test prompt",
            tokens_spent=1,
        )

        assert task.id is not None
        assert task.status == "pending"
        assert task.task_type == "generate"

    @pytest.mark.asyncio
    async def test_update_status(self, test_session: AsyncSession):
        """Test updating task status."""
        user_repo = UserRepository(test_session)
        task_repo = TaskRepository(test_session)

        user, _ = await user_repo.get_or_create(telegram_id=321321321)
        task = await task_repo.create(
            user_id=user.id,
            task_type="edit",
            prompt="Edit prompt",
            tokens_spent=2,
        )

        updated = await task_repo.update_status(
            task_id=task.id,
            status="done",
            result_image_url="https://example.com/image.png",
        )

        assert updated.status == "done"
        assert updated.result_image_url == "https://example.com/image.png"

    @pytest.mark.asyncio
    async def test_get_user_history(self, test_session: AsyncSession):
        """Test getting user's generation history."""
        user_repo = UserRepository(test_session)
        task_repo = TaskRepository(test_session)

        user, _ = await user_repo.get_or_create(telegram_id=456456456)
        
        # Create multiple tasks
        for i in range(5):
            await task_repo.create(
                user_id=user.id,
                task_type="generate",
                prompt=f"Prompt {i}",
                tokens_spent=1,
            )

        history = await task_repo.get_user_history(user.id, limit=3)
        assert len(history) == 3
