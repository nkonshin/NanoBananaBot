"""Tests for service layer - BalanceService and templates."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User, GenerationTask
from bot.db.repositories import UserRepository, TaskRepository
from bot.services.balance import BalanceService, InsufficientBalanceError
from bot.templates.prompts import (
    TEMPLATES,
    PromptTemplate,
    get_template_by_id,
    get_all_templates,
)


class TestBalanceService:
    """Tests for BalanceService."""

    @pytest.mark.asyncio
    async def test_check_balance_sufficient(self, test_session: AsyncSession):
        """Test checking balance when user has enough tokens."""
        user_repo = UserRepository(test_session)
        user, _ = await user_repo.get_or_create(telegram_id=100100100)
        
        balance_service = BalanceService(test_session)
        has_balance = await balance_service.check_balance(user.id, 5)
        
        assert has_balance is True

    @pytest.mark.asyncio
    async def test_check_balance_insufficient(self, test_session: AsyncSession):
        """Test checking balance when user doesn't have enough tokens."""
        user_repo = UserRepository(test_session)
        user, _ = await user_repo.get_or_create(telegram_id=100100101)
        
        balance_service = BalanceService(test_session)
        has_balance = await balance_service.check_balance(user.id, 100)
        
        assert has_balance is False

    @pytest.mark.asyncio
    async def test_deduct_tokens_success(self, test_session: AsyncSession):
        """Test successful token deduction."""
        user_repo = UserRepository(test_session)
        user, _ = await user_repo.get_or_create(telegram_id=100100102)
        initial_tokens = user.tokens
        
        balance_service = BalanceService(test_session)
        updated_user = await balance_service.deduct_tokens(user.id, 3)
        
        assert updated_user.tokens == initial_tokens - 3

    @pytest.mark.asyncio
    async def test_deduct_tokens_insufficient_raises(self, test_session: AsyncSession):
        """Test that deducting more tokens than available raises error."""
        user_repo = UserRepository(test_session)
        user, _ = await user_repo.get_or_create(telegram_id=100100103)
        
        balance_service = BalanceService(test_session)
        
        with pytest.raises(InsufficientBalanceError) as exc_info:
            await balance_service.deduct_tokens(user.id, 100)
        
        assert exc_info.value.required == 100
        assert exc_info.value.available == 10

    @pytest.mark.asyncio
    async def test_refund_tokens(self, test_session: AsyncSession):
        """Test refunding tokens to user."""
        user_repo = UserRepository(test_session)
        user, _ = await user_repo.get_or_create(telegram_id=100100104)
        initial_tokens = user.tokens
        
        balance_service = BalanceService(test_session)
        updated_user = await balance_service.refund_tokens(user.id, 5)
        
        assert updated_user.tokens == initial_tokens + 5

    @pytest.mark.asyncio
    async def test_refund_task(self, test_session: AsyncSession):
        """Test refunding tokens for a failed task."""
        user_repo = UserRepository(test_session)
        task_repo = TaskRepository(test_session)
        
        user, _ = await user_repo.get_or_create(telegram_id=100100105)
        
        # Deduct tokens first
        balance_service = BalanceService(test_session)
        await balance_service.deduct_tokens(user.id, 3)
        
        # Create a task
        task = await task_repo.create(
            user_id=user.id,
            task_type="generate",
            prompt="Test prompt",
            tokens_spent=3,
        )
        
        # Refund the task
        updated_user = await balance_service.refund_task(task.id)
        
        assert updated_user.tokens == 10  # Back to initial


class TestPromptTemplates:
    """Tests for prompt templates."""

    def test_templates_not_empty(self):
        """Test that templates list is not empty."""
        assert len(TEMPLATES) > 0

    def test_templates_have_required_fields(self):
        """Test that all templates have required fields."""
        for template in TEMPLATES:
            assert template.id is not None and template.id != ""
            assert template.name is not None and template.name != ""
            assert template.description is not None and template.description != ""
            assert template.prompt is not None and template.prompt != ""
            assert template.tokens_cost > 0

    def test_get_template_by_id_found(self):
        """Test getting a template by valid ID."""
        template = get_template_by_id("cyberpunk_portrait")
        
        assert template is not None
        assert template.id == "cyberpunk_portrait"
        assert "Киберпанк" in template.name

    def test_get_template_by_id_not_found(self):
        """Test getting a template by invalid ID."""
        template = get_template_by_id("nonexistent_template")
        
        assert template is None

    def test_get_all_templates(self):
        """Test getting all templates."""
        templates = get_all_templates()
        
        assert len(templates) == 3
        assert all(isinstance(t, PromptTemplate) for t in templates)

    def test_templates_have_unique_ids(self):
        """Test that all template IDs are unique."""
        ids = [t.id for t in TEMPLATES]
        assert len(ids) == len(set(ids))
