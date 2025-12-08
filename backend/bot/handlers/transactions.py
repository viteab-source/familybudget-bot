"""
bot/handlers/transactions.py — Команды для транзакций (расходы, доходы)
"""

from aiogram import types
from aiogram.filters import Command

from bot.config import logger
from bot.api_client import (
    api_create_transaction,
    api_get_last_transaction,
    api_delete_last_transaction,
    api_edit_last_transaction,
)
from bot.ui_helpers import send_tx_confirmation


async def cmd_add(message: types.Message):
    """Добавить расход: /add 100 Еда"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "Использование: /add *сумма* *категория*\n"
            "Пример: /add 100 Еда"
        )
        return
    
    try:
        amount = float(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    category = args[2].strip()
    
    try:
        tx = await api_create_transaction(
            message.from_user.id,
            amount=amount,
            category=category,
            kind="expense"
        )
        
        await send_tx_confirmation(
            message,
            tx,
            source_text=message.text,
            prefix="✅ Расход записан:"
        )
    except Exception as e:
        logger.error(f"Error in cmd_add: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_income(message: types.Message):
    """Добавить доход: /income 1000 Зарплата"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "Использование: /income *сумма* *категория*\n"
            "Пример: /income 1000 Зарплата"
        )
        return
    
    try:
        amount = float(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    category = args[2].strip()
    
    try:
        tx = await api_create_transaction(
            message.from_user.id,
            amount=amount,
            category=category,
            kind="income"
        )
        
        await send_tx_confirmation(
            message,
            tx,
            source_text=message.text,
            prefix="✅ Доход записан:"
        )
    except Exception as e:
        logger.error(f"Error in cmd_income: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_last(message: types.Message):
    """Показать последнюю транзакцию"""
    try:
        tx = await api_get_last_transaction(message.from_user.id)
        
        await send_tx_confirmation(
            message,
            tx,
            source_text="Последняя транзакция"
        )
    except Exception as e:
        logger.error(f"Error in cmd_last: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_del_last(message: types.Message):
    """Удалить последнюю транзакцию"""
    try:
        deleted = await api_delete_last_transaction(message.from_user.id)
        
        text = f"""
🗑️ **Транзакция удалена:**

Сумма: {deleted.get('amount')} {deleted.get('currency')}
Категория: {deleted.get('category')}
"""
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_del_last: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_edit_last(message: types.Message):
    """Изменить последнюю транзакцию: /edit_last 150"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "Использование: /edit_last *новая_сумма*\n"
            "Пример: /edit_last 150"
        )
        return
    
    try:
        new_amount = float(args[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    try:
        tx = await api_edit_last_transaction(
            message.from_user.id,
            new_amount=new_amount
        )
        
        await send_tx_confirmation(
            message,
            tx,
            source_text="Изменена последняя транзакция",
            prefix="✅ Транзакция обновлена:"
        )
    except Exception as e:
        logger.error(f"Error in cmd_edit_last: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
