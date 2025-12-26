"""Handler for Ideas and Trends (Идеи и тренды)."""

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.config import config
from bot.db.database import get_session_maker
from bot.db.repositories import UserRepository, TaskRepository
from bot.services.balance import BalanceService, InsufficientBalanceError
from bot.services.image_tokens import estimate_image_tokens, is_valid_quality, is_valid_size
from bot.templates.prompts import get_template_by_id, get_all_templates
from bot.keyboards.inline import (
    CallbackData,
    templates_keyboard,
    image_settings_confirm_keyboard,
    back_keyboard,
    main_menu_keyboard,
)
from bot.states.generation import TemplateStates

logger = logging.getLogger(__name__)

router = Router(name="trends")


# Note: Main trends menu is handled in menu.py
# This router handles template selection and confirmation


def _build_template_confirmation_text(
    template_name: str,
    template_description: str,
    template_prompt: str,
    balance: int,
    cost: int,
    quality: str,
    size: str,
    model: str,
    second_confirm: bool = False,
) -> str:
    prompt_preview = template_prompt[:300] + "..." if len(template_prompt) > 300 else template_prompt
    confirm_line = "Создать изображение по этому шаблону ещё раз?" if second_confirm else "Создать изображение по этому шаблону?"
    return (
        f"💡 <b>{template_name}</b>\n\n"
        f"<b>Описание:</b>\n{template_description}\n\n"
        f"<b>Промпт:</b>\n<i>{prompt_preview}</i>\n\n"
        f"<b>Модель:</b> {model}\n"
        f"<b>Качество:</b> {quality}\n"
        f"<b>Формат:</b> {size}\n\n"
        f"<b>Стоимость:</b> {cost} 🪙\n"
        f"<b>Ваш баланс:</b> {balance} 🪙\n"
        f"<b>После генерации:</b> {balance - cost} 🪙\n\n"
        f"{confirm_line}"
    )


@router.callback_query(F.data.startswith(CallbackData.TEMPLATE_PREFIX))
async def select_template(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle template selection from trends menu."""
    # Extract template_id from callback data
    template_id = callback.data.replace(CallbackData.TEMPLATE_PREFIX, "")
    
    template = get_template_by_id(template_id)
    
    if template is None:
        await callback.answer("❌ Шаблон не найден")
        return
    
    # Get user info and balance
    user_tg = callback.from_user
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_tg.id)
        
        if user is None:
            await callback.message.edit_text(
                "❌ Пользователь не найден. Используйте /start",
                reply_markup=main_menu_keyboard(),
            )
            await callback.answer()
            return
        
        balance = user.tokens
        quality = user.image_quality
        size = user.image_size
        model = user.selected_model

    cost = estimate_image_tokens(quality, size) * template.tokens_cost
    
    # Save template to state
    await state.update_data(
        template_id=template_id,
        user_id=user.id,
        image_quality=quality,
        image_size=size,
        model=model,
        expensive_confirmed=False,
    )
    await state.set_state(TemplateStates.confirm_template)
    
    # Show template details and confirmation
    await callback.message.edit_text(
        text=_build_template_confirmation_text(
            template_name=template.name,
            template_description=template.description,
            template_prompt=template.prompt,
            balance=balance,
            cost=cost,
            quality=quality,
            size=size,
            model=model,
        ),
        reply_markup=image_settings_confirm_keyboard(quality, size),
    )
    await callback.answer()


@router.callback_query(
    TemplateStates.confirm_template,
    F.data.startswith(CallbackData.IMAGE_QUALITY_PREFIX),
)
async def set_template_quality(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle quality selection while confirming template generation."""

    value = callback.data.replace(CallbackData.IMAGE_QUALITY_PREFIX, "")
    if not is_valid_quality(value):
        await callback.answer("❌ Неверное качество")
        return

    data = await state.get_data()
    template_id = data.get("template_id")
    user_id = data.get("user_id")
    size = data.get("image_size")
    model = data.get("model")

    if not template_id or not user_id or not size or not model:
        await callback.answer("❌ Ошибка состояния")
        await state.clear()
        return

    template = get_template_by_id(template_id)
    if template is None:
        await callback.answer("❌ Шаблон не найден")
        await state.clear()
        return

    await state.update_data(image_quality=value, expensive_confirmed=False)

    session_maker = get_session_maker()
    async with session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_image_settings(user_id=user_id, image_quality=value)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        balance = user.tokens if user else 0

    cost = estimate_image_tokens(value, size) * template.tokens_cost
    await callback.message.edit_text(
        text=_build_template_confirmation_text(
            template_name=template.name,
            template_description=template.description,
            template_prompt=template.prompt,
            balance=balance,
            cost=cost,
            quality=value,
            size=size,
            model=model,
        ),
        reply_markup=image_settings_confirm_keyboard(value, size),
    )
    await callback.answer()


@router.callback_query(
    TemplateStates.confirm_template,
    F.data.startswith(CallbackData.IMAGE_SIZE_PREFIX),
)
async def set_template_size(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle size selection while confirming template generation."""

    value = callback.data.replace(CallbackData.IMAGE_SIZE_PREFIX, "")
    if not is_valid_size(value):
        await callback.answer("❌ Неверный формат")
        return

    data = await state.get_data()
    template_id = data.get("template_id")
    user_id = data.get("user_id")
    quality = data.get("image_quality")
    model = data.get("model")

    if not template_id or not user_id or not quality or not model:
        await callback.answer("❌ Ошибка состояния")
        await state.clear()
        return

    template = get_template_by_id(template_id)
    if template is None:
        await callback.answer("❌ Шаблон не найден")
        await state.clear()
        return

    await state.update_data(image_size=value, expensive_confirmed=False)

    session_maker = get_session_maker()
    async with session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_image_settings(user_id=user_id, image_size=value)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        balance = user.tokens if user else 0

    cost = estimate_image_tokens(quality, value) * template.tokens_cost
    await callback.message.edit_text(
        text=_build_template_confirmation_text(
            template_name=template.name,
            template_description=template.description,
            template_prompt=template.prompt,
            balance=balance,
            cost=cost,
            quality=quality,
            size=value,
            model=model,
        ),
        reply_markup=image_settings_confirm_keyboard(quality, value),
    )
    await callback.answer()


@router.callback_query(TemplateStates.confirm_template, F.data == CallbackData.CONFIRM)
async def confirm_template_generation(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Confirm and start generation from template.
    
    - Deducts tokens
    - Creates GenerationTask with template prompt
    - Enqueues task to RQ
    """
    data = await state.get_data()
    template_id = data.get("template_id")
    user_id = data.get("user_id")
    quality = data.get("image_quality")
    size = data.get("image_size")
    model = data.get("model")
    expensive_confirmed = data.get("expensive_confirmed", False)
    
    if not template_id or not user_id or not quality or not size or not model:
        await callback.message.edit_text(
            "❌ Ошибка: данные сессии потеряны. Попробуйте снова.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return
    
    template = get_template_by_id(template_id)
    
    if template is None:
        await callback.message.edit_text(
            "❌ Шаблон не найден.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        balance_service = BalanceService(session)
        task_repo = TaskRepository(session)
        
        try:
            cost = estimate_image_tokens(quality, size) * template.tokens_cost

            if cost >= config.high_cost_threshold and not expensive_confirmed:
                user_repo = UserRepository(session)
                user = await user_repo.get_by_telegram_id(callback.from_user.id)
                balance = user.tokens if user else 0

                await state.update_data(expensive_confirmed=True)
                await callback.message.edit_text(
                    text=_build_template_confirmation_text(
                        template_name=template.name,
                        template_description=template.description,
                        template_prompt=template.prompt,
                        balance=balance,
                        cost=cost,
                        quality=quality,
                        size=size,
                        model=model,
                        second_confirm=True,
                    ),
                    reply_markup=image_settings_confirm_keyboard(
                        quality,
                        size,
                        confirm_callback_data=CallbackData.EXPENSIVE_CONFIRM,
                    ),
                )
                await callback.answer("Подтвердите ещё раз")
                return

            # Deduct tokens
            await balance_service.deduct_tokens(user_id, cost)
            
            # Create task with template prompt
            task = await task_repo.create(
                user_id=user_id,
                task_type="generate",
                prompt=template.prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
            )
            
            logger.info(
                f"Created template task {task.id} for user {user_id} "
                f"(template: {template_id})"
            )
            
        except InsufficientBalanceError as e:
            await callback.message.edit_text(
                text=(
                    f"❌ <b>Недостаточно токенов</b>\n\n"
                    f"Требуется: {e.required} 🪙\n"
                    f"Ваш баланс: {e.available} 🪙\n\n"
                    "Пополните баланс в разделе «Купить токены»"
                ),
                reply_markup=main_menu_keyboard(),
            )
            await state.clear()
            await callback.answer()
            return
    
    # Clear state
    await state.clear()
    
    # Enqueue task to RQ
    try:
        from bot.tasks.generation import enqueue_generation_task
        enqueue_generation_task(task.id)
    except Exception as e:
        logger.error(f"Failed to enqueue task {task.id}: {e}")
    
    await callback.message.edit_text(
        text=(
            f"✅ <b>Задача создана!</b>\n\n"
            f"🆔 ID задачи: <code>{task.id}</code>\n"
            f"📝 Шаблон: {template.name}\n\n"
            "⏳ Ваше изображение генерируется...\n"
            "Я отправлю результат, когда будет готово.\n\n"
            "Это может занять 10-30 секунд."
        ),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Генерация запущена! ⏳")


@router.callback_query(
    TemplateStates.confirm_template,
    F.data == CallbackData.EXPENSIVE_CONFIRM,
)
async def confirm_template_generation_expensive(callback: CallbackQuery, state: FSMContext) -> None:
    """Second step confirmation for expensive template generation."""

    data = await state.get_data()
    template_id = data.get("template_id")
    user_id = data.get("user_id")
    quality = data.get("image_quality")
    size = data.get("image_size")
    model = data.get("model")

    if not template_id or not user_id or not quality or not size or not model:
        await callback.message.edit_text(
            "❌ Ошибка: данные сессии потеряны. Попробуйте снова.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    template = get_template_by_id(template_id)
    if template is None:
        await callback.message.edit_text(
            "❌ Шаблон не найден.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    cost = estimate_image_tokens(quality, size) * template.tokens_cost

    session_maker = get_session_maker()
    async with session_maker() as session:
        balance_service = BalanceService(session)
        task_repo = TaskRepository(session)

        try:
            await balance_service.deduct_tokens(user_id, cost)

            task = await task_repo.create(
                user_id=user_id,
                task_type="generate",
                prompt=template.prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
            )

            logger.info(
                f"Created template task {task.id} for user {user_id} "
                f"(template: {template_id})"
            )

        except InsufficientBalanceError as e:
            await callback.message.edit_text(
                text=(
                    f"❌ <b>Недостаточно токенов</b>\n\n"
                    f"Требуется: {e.required} 🪙\n"
                    f"Ваш баланс: {e.available} 🪙\n\n"
                    "Пополните баланс в разделе «Купить токены»"
                ),
                reply_markup=main_menu_keyboard(),
            )
            await state.clear()
            await callback.answer()
            return

    await state.clear()

    try:
        from bot.tasks.generation import enqueue_generation_task
        enqueue_generation_task(task.id)
    except Exception as e:
        logger.error(f"Failed to enqueue task {task.id}: {e}")

    await callback.message.edit_text(
        text=(
            f"✅ <b>Задача создана!</b>\n\n"
            f"🆔 ID задачи: <code>{task.id}</code>\n"
            f"📝 Шаблон: {template.name}\n\n"
            "⏳ Ваше изображение генерируется...\n"
            "Я отправлю результат, когда будет готово.\n\n"
            "Это может занять 10-30 секунд."
        ),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Генерация запущена! ⏳")


@router.callback_query(TemplateStates.confirm_template, F.data == CallbackData.CANCEL)
async def cancel_template_generation(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel template generation and return to templates list."""
    await state.clear()
    
    await callback.message.edit_text(
        text=(
            "💡 <b>Идеи и тренды</b>\n\n"
            "Выберите готовый шаблон для быстрой генерации:"
        ),
        reply_markup=templates_keyboard(),
    )
    await callback.answer("Отменено")
