"""
bot/handlers/callbacks.py — Обработчики callback_query (кнопки, inline меню)
"""

import asyncio
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import logger
from bot.api_client import (
    api_set_last_transaction_category,
    api_leave_household,
    api_mark_reminder_paid,
    api_log_category_feedback,
)
from bot.cache import (
    pending_manual_category,
    pending_family_leave_confirmations,
    ai_suggestions_cache,
    _clear_family_leave_confirmation,
)


async def handle_category_selection(callback_query: types.CallbackQuery):
    """
    Обработчик кнопок выбора категории:
    callback_data = "setcat_ai:TX_ID:CATEGORY_NAME"
    """
    
    if not callback_query.data.startswith("setcat_ai:"):
        return
    
    try:
        parts = callback_query.data.split(":", 2)
        if len(parts) != 3:
            await callback_query.answer("❌ Ошибка формата кнопки", show_alert=True)
            return
        
        tx_id = int(parts[1])
        chosen_category = parts[2]
        
        user_id = callback_query.from_user.id
        
        # Устанавливаем категорию
        await api_set_last_transaction_category(user_id, chosen_category)
        
        # Логируем выбор (если данные в кэше)
        key = (user_id, tx_id)
        cached = ai_suggestions_cache.get(key)
        
        if cached:
            await api_log_category_feedback(
                telegram_id=user_id,
                transaction_id=tx_id,
                original_category=cached.get("ai_category"),
                chosen_category=chosen_category,
                candidate_categories=cached.get("candidate_categories", []),
                original_text=cached.get("original_text"),
            )
            
            # Удаляем из кэша
            del ai_suggestions_cache[key]
        
        await callback_query.message.edit_text(
            f"✅ Категория установлена: {chosen_category}"
        )
        await callback_query.answer("✅ Сохранено!", show_alert=False)
        
    except Exception as e:
        logger.error(f"Error in handle_category_selection: {e}")
        await callback_query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


async def handle_category_other(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Нет подходящей категории":
    callback_data = "setcat_ai_other:TX_ID"
    """
    
    if not callback_query.data.startswith("setcat_ai_other:"):
        return
    
    try:
        tx_id = int(callback_query.data.split(":", 1)[1])
        user_id = callback_query.from_user.id
        
        # Добавляем в очередь ожидания ввода категории
        pending_manual_category[user_id] = {"tx_id": tx_id}
        
        await callback_query.message.edit_text(
            "Напиши название правильной категории:"
        )
        
        # Автоочистка через 60 секунд
        async def cleanup():
            await asyncio.sleep(60)
            pending_manual_category.pop(user_id, None)
        
        asyncio.create_task(cleanup())
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in handle_category_other: {e}")
        await callback_query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


async def handle_family_leave_confirm(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки подтверждения выхода из семьи:
    callback_data = "family_leave_confirm"
    """
    
    if callback_query.data not in ["family_leave_confirm", "family_leave_cancel"]:
        return
    
    user_id = callback_query.from_user.id
    
    if callback_query.data == "family_leave_cancel":
        # Отмена
        pending_family_leave_confirmations.discard(user_id)
        await callback_query.message.edit_text("❌ Выход отменен")
        await callback_query.answer()
        return
    
    # Подтверждение выхода
    if user_id not in pending_family_leave_confirmations:
        await callback_query.answer("⏰ Время действия ссылки истекло", show_alert=True)
        return
    
    try:
        result = await api_leave_household(user_id)
        
        pending_family_leave_confirmations.discard(user_id)
        
        await callback_query.message.edit_text(
            "✅ Ты вышел из семьи.\n\n"
            "Твои данные сохранены, но ты больше не видишь данные семьи."
        )
        await callback_query.answer("✅ Готово", show_alert=False)
        
    except Exception as e:
        logger.error(f"Error in handle_family_leave_confirm: {e}")
        await callback_query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


async def handle_reminder_paid(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки отметить напоминание как оплачено:
    callback_data = "reminder_paid:REMINDER_ID"
    """
    
    if not callback_query.data.startswith("reminder_paid:"):
        return
    
    try:
        reminder_id = int(callback_query.data.split(":", 1)[1])
        
        result = await api_mark_reminder_paid(
            reminder_id,
            telegram_id=callback_query.from_user.id
        )
        
        await callback_query.message.edit_text(
            "✅ Напоминание отмечено как оплаченное"
        )
        await callback_query.answer("✅", show_alert=False)
        
    except Exception as e:
        logger.error(f"Error in handle_reminder_paid: {e}")
        await callback_query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
