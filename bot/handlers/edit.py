"""Handler for image editing flow."""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize
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
from bot.states.generation import EditStates

logger = logging.getLogger(__name__)

router = Router(name="edit")


def _build_confirmation_text(
    prompt: str,
    balance: int,
    cost: int,
    quality: str,
    size: str,
    model: str,
    second_confirm: bool = False,
) -> str:
    prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
    confirm_line = "Подтвердить редактирование ещё раз?" if second_confirm else "Подтвердить редактирование?"
    return (
        f"✏️ <b>Подтверждение редактирования</b>\n\n"
        f"<b>Описание изменений:</b>\n<i>{prompt_preview}</i>\n\n"
        f"<b>Модель:</b> {model}\n"
        f"<b>Качество:</b> {quality}\n"
        f"<b>Формат:</b> {size}\n\n"
        f"<b>Стоимость:</b> {cost} 🪙\n"
        f"<b>Ваш баланс:</b> {balance} 🪙\n"
        f"<b>После редактирования:</b> {balance - cost} 🪙\n\n"
        f"{confirm_line}"
    )

# Supported image formats
SUPPORTED_FORMATS = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_image_format(file_name: str | None, mime_type: str | None) -> bool:
    """
    Validate that the image format is supported.
    
    Args:
        file_name: Original file name
        mime_type: MIME type of the file
    
    Returns:
        True if format is supported, False otherwise
    """
    # Check MIME type
    if mime_type and mime_type.lower() in SUPPORTED_FORMATS:
        return True
    
    # Check file extension
    if file_name:
        file_name_lower = file_name.lower()
        for ext in SUPPORTED_EXTENSIONS:
            if file_name_lower.endswith(ext):
                return True
    
    return False


@router.message(EditStates.waiting_image, F.photo)
async def process_photo(message: Message, state: FSMContext) -> None:
    """
    Process uploaded photo for editing.
    
    Saves file_id and asks for edit description.
    """
    # Get the largest photo size
    photo: PhotoSize = message.photo[-1]
    file_id = photo.file_id
    
    # Get user info
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
    
    # Save photo file_id to state
    await state.update_data(
        source_file_id=file_id,
        user_id=user.id,
    )
    await state.set_state(EditStates.waiting_edit_prompt)
    
    await message.answer(
        text=(
            "✅ <b>Фото получено!</b>\n\n"
            "Теперь опишите, какие изменения вы хотите внести.\n\n"
            "💡 <i>Примеры:</i>\n"
            "• «Сделай фон размытым»\n"
            "• «Добавь закат на заднем плане»\n"
            "• «Преврати в мультяшный стиль»"
        ),
        reply_markup=back_keyboard(),
    )


@router.message(EditStates.waiting_image, F.document)
async def process_document_image(message: Message, state: FSMContext) -> None:
    """
    Process uploaded document (image file) for editing.
    
    Validates format and saves file_id.
    """
    document = message.document
    
    # Validate format
    if not validate_image_format(document.file_name, document.mime_type):
        await message.answer(
            text=(
                "❌ <b>Неподдерживаемый формат</b>\n\n"
                "Пожалуйста, отправьте изображение в одном из форматов:\n"
                "• JPG / JPEG\n"
                "• PNG\n"
                "• WEBP\n\n"
                "Или отправьте фото напрямую (не как файл)."
            ),
            reply_markup=back_keyboard(),
        )
        return
    
    file_id = document.file_id
    
    # Get user info
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
    
    # Save file_id to state
    await state.update_data(
        source_file_id=file_id,
        user_id=user.id,
    )
    await state.set_state(EditStates.waiting_edit_prompt)
    
    await message.answer(
        text=(
            "✅ <b>Изображение получено!</b>\n\n"
            "Теперь опишите, какие изменения вы хотите внести."
        ),
        reply_markup=back_keyboard(),
    )


@router.message(EditStates.waiting_image)
async def invalid_image_input(message: Message) -> None:
    """Handle invalid input when waiting for image."""
    await message.answer(
        text=(
            "❌ Пожалуйста, отправьте изображение.\n\n"
            "📎 <i>Поддерживаемые форматы: JPG, PNG, WEBP</i>"
        ),
        reply_markup=back_keyboard(),
    )


@router.message(EditStates.waiting_edit_prompt, F.text)
async def process_edit_prompt(message: Message, state: FSMContext) -> None:
    """
    Process the edit description/prompt.
    
    Shows cost and asks for confirmation.
    """
    prompt = message.text.strip()
    
    if not prompt:
        await message.answer(
            "❌ Пожалуйста, опишите желаемые изменения.",
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
    data = await state.get_data()
    user_id = data.get("user_id")
    
    session_maker = get_session_maker()
    
    async with session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
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
        image_quality=quality,
        image_size=size,
        model=model,
        expensive_confirmed=False,
    )
    await state.set_state(EditStates.confirm_edit)
    
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
    EditStates.confirm_edit,
    F.data.startswith(CallbackData.IMAGE_QUALITY_PREFIX),
)
async def set_edit_quality(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle quality selection while confirming edit."""

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
    EditStates.confirm_edit,
    F.data.startswith(CallbackData.IMAGE_SIZE_PREFIX),
)
async def set_edit_size(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle size selection while confirming edit."""

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


@router.message(EditStates.waiting_edit_prompt)
async def invalid_edit_prompt_input(message: Message) -> None:
    """Handle non-text input when waiting for edit prompt."""
    await message.answer(
        "❌ Пожалуйста, отправьте текстовое описание изменений.",
        reply_markup=back_keyboard(),
    )


@router.callback_query(EditStates.confirm_edit, F.data == CallbackData.CONFIRM)
async def confirm_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Confirm and start the edit task.
    
    - Deducts tokens
    - Creates GenerationTask with type 'edit'
    - Enqueues task to RQ
    """
    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = data.get("user_id")
    source_file_id = data.get("source_file_id")
    quality = data.get("image_quality")
    size = data.get("image_size")
    model = data.get("model")
    expensive_confirmed = data.get("expensive_confirmed", False)
    
    if not prompt or not user_id or not source_file_id or not quality or not size or not model:
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
        
        try:
            # Deduct tokens
            await balance_service.deduct_tokens(user_id, cost)
            
            # Create task with source image
            task = await task_repo.create(
                user_id=user_id,
                task_type="edit",
                prompt=prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
                source_image_url=source_file_id,  # Store file_id as source
            )
            
            logger.info(f"Created edit task {task.id} for user {user_id}")
            
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
            "✅ <b>Задача создана!</b>\n\n"
            f"🆔 ID задачи: <code>{task.id}</code>\n\n"
            "⏳ Ваше изображение редактируется...\n"
            "Я отправлю результат, когда будет готово.\n\n"
            "Это может занять 10-30 секунд."
        ),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Редактирование запущено! ⏳")


@router.callback_query(
    EditStates.confirm_edit,
    F.data == CallbackData.EXPENSIVE_CONFIRM,
)
async def confirm_edit_expensive(callback: CallbackQuery, state: FSMContext) -> None:
    """Second step confirmation for expensive edit."""

    data = await state.get_data()
    prompt = data.get("prompt")
    user_id = data.get("user_id")
    source_file_id = data.get("source_file_id")
    quality = data.get("image_quality")
    size = data.get("image_size")
    model = data.get("model")

    if not prompt or not user_id or not source_file_id or not quality or not size or not model:
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

        try:
            await balance_service.deduct_tokens(user_id, cost)

            task = await task_repo.create(
                user_id=user_id,
                task_type="edit",
                prompt=prompt,
                tokens_spent=cost,
                model=model,
                image_quality=quality,
                image_size=size,
                source_image_url=source_file_id,
            )

            logger.info(f"Created edit task {task.id} for user {user_id}")

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
            "⏳ Ваше изображение редактируется...\n"
            "Я отправлю результат, когда будет готово.\n\n"
            "Это может занять 10-30 секунд."
        ),
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Редактирование запущено! ⏳")


@router.callback_query(EditStates.confirm_edit, F.data == CallbackData.CANCEL)
async def cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the edit and return to menu."""
    await state.clear()
    
    await callback.message.edit_text(
        text="❌ Редактирование отменено.\n\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Отменено")
