"""
bot/handlers/reminders.py — Команды для напоминаний
"""

from aiogram import types
from aiogram.filters import Command

from bot.config import logger
from bot.api_client import (
    api_create_reminder,
    api_list_reminders,
    api_get_due_reminders,
)


async def cmd_reminders(message: types.Message):
    """Список активных напоминаний"""
    try:
        reminders = await api_list_reminders(message.from_user.id)
        
        if not reminders:
            await message.answer("⏰ Нет активных напоминаний")
            return
        
        lines = ["⏰ **Активные напоминания:**", ""]
        
        for rem in reminders:
            title = rem.get('title', 'N/A')
            amount = rem.get('amount')
            interval = rem.get('interval_days')
            
            interval_text = f"каждые {interval} дней" if interval else "однократное"
            amount_text = f", {amount} RUB" if amount else ""
            
            lines.append(f"• {title}{amount_text} ({interval_text})")
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_reminders: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_remind_list(message: types.Message):
    """Показать напоминания к оплате"""
    try:
        due = await api_get_due_reminders(message.from_user.id)
        
        if not due:
            await message.answer("✅ Сегодня нечего не нужно платить!")
            return
        
        lines = ["🔔 **Напоминания к оплате:**", ""]
        
        for rem in due:
            title = rem.get('title', 'N/A')
            amount = rem.get('amount')
            
            amount_text = f", {amount} RUB" if amount else ""
            lines.append(f"• {title}{amount_text}")
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_remind_list: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_remind_add(message: types.Message):
    """
    Добавить напоминание:
    /remind_add интернет 500 30
    (напоминание 'интернет', 500 рублей, каждые 30 дней)
    """
    args = message.text.split(maxsplit=3)
    
    if len(args) < 2:
        await message.answer(
            "Использование: /remind_add *описание* [сумма] [интервал_дней]\n"
            "Пример: /remind_add интернет 500 30"
        )
        return
    
    title = args[1]
    amount = None
    interval_days = None
    
    if len(args) > 2:
        try:
            amount = float(args[2])
        except ValueError:
            pass
    
    if len(args) > 3:
        try:
            interval_days = int(args[3])
        except ValueError:
            pass
    
    try:
        result = await api_create_reminder(
            message.from_user.id,
            title=title,
            amount=amount,
            interval_days=interval_days
        )
        
        interval_text = f" каждые {interval_days} дней" if interval_days else " (однократное)"
        amount_text = f" {amount} RUB," if amount else ""
        
        await message.answer(
            f"✅ Напоминание создано: {title},{amount_text}{interval_text}"
        )
    except Exception as e:
        logger.error(f"Error in cmd_remind_add: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
