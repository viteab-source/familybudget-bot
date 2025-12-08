"""
bot/handlers/ai_input.py — AI-powered input: голос, свободный текст
"""

from aiogram import types, F
from aiogram.filters import Command

from bot.config import logger, YANDEX_API_KEY
from bot.api_client import (
    api_parse_and_create,
    api_get_last_transaction,
)
from bot.ui_helpers import send_tx_confirmation, send_ai_category_suggestions
from bot.cache import pending_manual_category


async def cmd_aiadd(message: types.Message):
    """Начать ввод расхода через ИИ"""
    await message.answer(
        "🧠 Режим ИИ включен!\n\n"
        "Отправь сообщение со своим расходом в любом виде:\n"
        "• 'Купил хлеб на 100 рублей'\n"
        "• 'Кино на 500'\n"
        "• 'Такси до офиса'\n\n"
        "Я распознаю сумму и категорию автоматически!"
    )


async def handle_voice(message: types.Message):
    """Обработчик голосовых сообщений"""
    
    if not YANDEX_API_KEY:
        await message.answer("❌ Голосовые сообщения временно недоступны")
        return
    
    # Обработка голоса
    try:
        # TODO: реализовать STT если нужна
        pass
    except Exception as e:
        logger.error(f"Error processing voice: {e}")
        await message.answer(f"❌ Ошибка при обработке голоса: {str(e)}")


async def handle_free_text(message: types.Message):
    """
    Обработчик свободного текста для ИИ-парсинга.
    Это срабатывает когда пользователь пишет текст в режиме /aiadd
    """
    
    # Проверяем если пользователь ждёт ввода категории
    user_id = message.from_user.id
    
    if user_id in pending_manual_category:
        # Пользователь вводит категорию вручную
        data = pending_manual_category[user_id]
        tx_id = data.get("tx_id")
        
        # Здесь нужно установить категорию (реализовано в callbacks.py)
        await message.answer(
            "Эта логика обработана в callbacks.py (handle_category_other)"
        )
        return
    
    # Иначе, парсим текст через ИИ
    text = message.text.strip()
    
    if not text or len(text) < 3:
        await message.answer(
            "Слишком короткий текст. Напиши что-нибудь типа:\n"
            "'Купил хлеб на 100 рублей'"
        )
        return
    
    try:
        # Парсим и создаём транзакцию через ИИ
        tx = await api_parse_and_create(user_id, text)
        
        # Отправляем подтверждение
        await send_tx_confirmation(
            message,
            tx,
            source_text=text,
            via_ai=True,
            prefix="🧠 Распознал расход:"
        )
        
        # Показываем кнопки для выбора категории
        await send_ai_category_suggestions(
            message,
            tx,
            user_id,
            original_text=text
        )
        
    except Exception as e:
        logger.error(f"Error in handle_free_text: {e}")
        await message.answer(f"❌ Ошибка при парсинге: {str(e)}")
