"""Handler for image generation flow."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.config import config
from bot.db.database import get_session_maker
from bot.db.repositories import UserRepository, TaskRepository
from bot.services.balance import BalanceService, InsufficientBalanceError
from bot.services.image_tokens import estimate_image_tokens, is_valid_quality, is_valid_size
from bot.keyboards.inline import (
    CallbackData,
    image_settings_confirm_keyboard,
    back_keyboard,
    main_menu_keyboard,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router(name="generate")


def _build_confirmation_text(
    prompt: str,
    balance: int,
    cost: int,
    quality: str,
    size: str,
    model: str,
    second_confirm: bool = False,
) -> str:
    warning = "\n⚠️ <b>Внимание:</b> дорогая генерация." if cost >= config.high_cost_threshold else ""

    confirm_line = "Подтвердить генерацию ещё раз?" if second_confirm else "Подтвердить генерацию?"

    return (
        f"🎨 <b>Подтверждение генерации</b>\n\n"
        f"<b>Ваш промпт:</b>\n<i>{prompt[:500]}{'...' if len(prompt) > 500 else ''}</i>\n\n"
        f"<b>Модель:</b> {model}\n"
        f"<b>Качество:</b> {quality}\n"
        f"<b>Формат:</b> {size}\n\n"
        f"<b>Стоимость:</b> {cost} 🪙\n"
        f"<b>Ваш баланс:</b> {balance} 🪙\n"
        f"<b>После генерации:</b> {balance - cost} 🪙\n"
        f"{warning}\n\n"
        f"{confirm_line}"
    )


@router.message(GenerationStates.waiting_prompt, F.text)
async def process_prompt(message: Message, state: FSMContext) -> None:
    """
    Process the user's prompt for image generation.
    
    Shows cost and asks for confirmation.
    """
    prompt = message.text.strip()
    
    if not prompt:
        await message.answer(
            "❌ Пожалуйста, введите описание изображения.",
            reply_markup=back_keyboard(),
        )
        return
    
    if len(prompt) > 2000:
        await message.answer(
            "❌ Описание слишком длинное. Максимум 2000 символов.",
            reply_markup=back_keyboard(),
        )
        return
    
    # Get user balance
    user_tg = message.from_user
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_tg.id)
        
        if user is None:
            await message.answer(
                "❌ Пользователь не найден. Используйте /start",
                reply_markup=back_keyboard(),
            )
            await state.clear()
            return
        
        balance = user.tokens
        quality = user.image_quality
        size = user.image_size
        model = user.selected_model

    cost = estimate_image_tokens(quality, size)

    # Save prompt to state
    await state.update_data(
        prompt=prompt,
        user_id=user.id,
        image_quality=quality,
        image_size=size,
        model=model,
        expensive_confirmed=False,
    )
    await state.set_state(GenerationStates.confirm_generation)
    
    # Show confirmation
    await message.answer(
        text=_build_confirmation_text(
            prompt=prompt,
            balance=balance,
            cost=cost,
            quality=quality,
            size=size,
            model=model,
        ),
        reply_markup=image_settings_confirm_keyboard(quality, size),
    )


@router.callback_query(
    GenerationStates.confirm_generation,
    F.data.startswith(CallbackData.IMAGE_QUALITY_PREFIX),
)
async def set_generation_quality(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle quality selection while confirming generation."""

    value = callback.data.replace(CallbackData.IMAGE_QUALITY_PREFIX, "")
    if not is_valid_quality(value):
        await callback.answer("❌ Неверное качество")
        return

    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = data.get("user_id")
    size = data.get("image_size")
    model = data.get("model")

    if not prompt or not user_id or not size or not model:
        await callback.answer("❌ Ошибка состояния")
        await state.clear()
        return

    await state.update_data(image_quality=value, expensive_confirmed=False)

    session_maker = get_session_maker()
    async with session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_image_settings(user_id=user_id, image_quality=value)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        balance = user.tokens if user else 0

    cost = estimate_image_tokens(value, size)
    await callback.message.edit_text(
        text=_build_confirmation_text(
            prompt=prompt,
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
    GenerationStates.confirm_generation,
    F.data.startswith(CallbackData.IMAGE_SIZE_PREFIX),
)
async def set_generation_size(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle size selection while confirming generation."""

    value = callback.data.replace(CallbackData.IMAGE_SIZE_PREFIX, "")
    if not is_valid_size(value):
        await callback.answer("❌ Неверный формат")
        return

    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = data.get("user_id")
    quality = data.get("image_quality")
    model = data.get("model")

    if not prompt or not user_id or not quality or not model:
        await callback.answer("❌ Ошибка состояния")
        await state.clear()
        return

    await state.update_data(image_size=value, expensive_confirmed=False)

    session_maker = get_session_maker()
    async with session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_image_settings(user_id=user_id, image_size=value)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        balance = user.tokens if user else 0

    cost = estimate_image_tokens(quality, value)
    await callback.message.edit_text(
        text=_build_confirmation_text(
            prompt=prompt,
            balance=balance,
            cost=cost,
            quality=quality,
            size=value,
            model=model,
        ),
        reply_markup=image_settings_confirm_keyboard(quality, value),
    )
    await callback.answer()


@router.callback_query(GenerationStates.confirm_generation, F.data == CallbackData.CONFIRM)
async def confirm_generation(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Confirm and start the generation task.
    
    - Deducts tokens
    - Creates GenerationTask with status 'pending'
    - Enqueues task to RQ
    """
    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = data.get("user_id")
    quality = data.get("image_quality")
    size = data.get("image_size")
    expensive_confirmed = data.get("expensive_confirmed", False)

    if not prompt or not user_id or not quality or not size:
        await callback.message.edit_text(
            "❌ Ошибка: данные сессии потеряны. Попробуйте снова.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    cost = estimate_image_tokens(quality, size)

    if cost >= config.high_cost_threshold and not expensive_confirmed:
        session_maker = get_session_maker()
        async with session_maker() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            balance = user.tokens if user else 0
            model = user.selected_model if user else "gpt-image-1"

        await state.update_data(expensive_confirmed=True)
        await callback.message.edit_text(
            text=_build_confirmation_text(
                prompt=prompt,
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
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        balance_service = BalanceService(session)
        task_repo = TaskRepository(session)
        user_repo = UserRepository(session)

        try:
            # Deduct tokens
            await balance_service.deduct_tokens(user_id, cost)

            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            model = user.selected_model if user else "gpt-image-1"
            
            # Create task
            task = await task_repo.create(
                user_id=user_id,
                task_type="generate",
                prompt=prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
            )
            
            logger.info(f"Created generation task {task.id} for user {user_id}")
            
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
    
    # Enqueue task to RQ (import here to avoid circular imports)
    try:
        from bot.tasks.generation import enqueue_generation_task
        enqueue_generation_task(task.id)
    except Exception as e:
        logger.error(f"Failed to enqueue task {task.id}: {e}")
        # Task is created, worker will pick it up eventually
    
    await callback.message.edit_text(
        text=(
            "✅ <b>Задача создана!</b>\n\n"
            f"🆔 ID задачи: <code>{task.id}</code>\n\n"
            "⏳ Ваше изображение генерируется...\n"
            "Я отправлю результат, когда будет готово.\n\n"
            "Это может занять 10-30 секунд."
        ),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Генерация запущена! ⏳")


@router.callback_query(
    GenerationStates.confirm_generation,
    F.data == CallbackData.EXPENSIVE_CONFIRM,
)
async def confirm_generation_expensive(callback: CallbackQuery, state: FSMContext) -> None:
    """Second step confirmation for expensive generation."""

    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = data.get("user_id")
    quality = data.get("image_quality")
    size = data.get("image_size")

    if not prompt or not user_id or not quality or not size:
        await callback.message.edit_text(
            "❌ Ошибка: данные сессии потеряны. Попробуйте снова.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    cost = estimate_image_tokens(quality, size)

    session_maker = get_session_maker()
    async with session_maker() as session:
        balance_service = BalanceService(session)
        task_repo = TaskRepository(session)
        user_repo = UserRepository(session)

        try:
            await balance_service.deduct_tokens(user_id, cost)

            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            model = user.selected_model if user else "gpt-image-1"

            task = await task_repo.create(
                user_id=user_id,
                task_type="generate",
                prompt=prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
            )

            logger.info(f"Created generation task {task.id} for user {user_id}")

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
            "✅ <b>Задача создана!</b>\n\n"
            f"🆔 ID задачи: <code>{task.id}</code>\n\n"
            "⏳ Ваше изображение генерируется...\n"
            "Я отправлю результат, когда будет готово.\n\n"
            "Это может занять 10-30 секунд."
        ),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Генерация запущена! ⏳")


@router.callback_query(GenerationStates.confirm_generation, F.data == CallbackData.CANCEL)
async def cancel_generation(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the generation and return to menu."""
    await state.clear()
    
    await callback.message.edit_text(
        text="❌ Генерация отменена.\n\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Отменено")


@router.message(GenerationStates.waiting_prompt)
async def invalid_prompt_input(message: Message) -> None:
    """Handle non-text input when waiting for prompt."""
    await message.answer(
        "❌ Пожалуйста, отправьте текстовое описание изображения.",
        reply_markup=back_keyboard(),
    )
