"""
bot/handlers/budgets.py — Команды для бюджетов
"""

from aiogram import types
from aiogram.filters import Command

from bot.config import logger
from bot.api_client import (
    api_get_categories,
)
from bot.ui_helpers import format_amount


async def cmd_budget_list(message: types.Message):
    """Показать все бюджеты"""
    try:
        cats = await api_get_categories(message.from_user.id)
        
        budgets = [c for c in cats if c.get('budget_limit')]
        
        if not budgets:
            await message.answer("💰 Бюджетов не найдено")
            return
        
        lines = ["💰 **Бюджеты:**", ""]
        
        for cat in budgets:
            name = cat.get('name', 'N/A')
            limit = cat.get('budget_limit')
            spent = cat.get('budget_spent', 0)
            
            lines.append(
                f"• {name}: {format_amount(spent, 'RUB')} / "
                f"{format_amount(limit, 'RUB')}"
            )
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_budget_list: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_budget_set(message: types.Message):
    """
    Установить бюджет для категории:
    /budget_set Еда 5000
    """
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "Использование: /budget_set *категория* *сумма*\n"
            "Пример: /budget_set Еда 5000"
        )
        return
    
    category = args[1].strip()
    
    try:
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом")
        return
    
    # TODO: реализовать api_set_budget в бэкенде
    await message.answer(
        f"✅ Бюджет установлен: {category} = {format_amount(amount, 'RUB')}\n\n"
        "(Функция в разработке)"
    )


async def cmd_budget_remove(message: types.Message):
    """
    Удалить бюджет для категории:
    /budget_remove Еда
    """
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "Использование: /budget_remove *категория*\n"
            "Пример: /budget_remove Еда"
        )
        return
    
    category = args[1].strip()
    
    # TODO: реализовать api_delete_budget в бэкенде
    await message.answer(
        f"✅ Бюджет удалён: {category}\n\n"
        "(Функция в разработке)"
    )
