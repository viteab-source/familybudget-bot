"""
bot/handlers/categories.py — Команды для работы с категориями
"""

from aiogram import types
from aiogram.filters import Command

from bot.config import logger
from bot.api_client import (
    api_get_categories,
    api_create_category,
    api_delete_category,
    api_rename_category,
    api_merge_categories,
)


async def cmd_categories(message: types.Message):
    """Показать все категории"""
    try:
        cats = await api_get_categories(message.from_user.id)
        
        if not cats:
            await message.answer("📂 Категорий не найдено")
            return
        
        lines = ["📂 **Категории:**", ""]
        for cat in cats:
            name = cat.get('name', 'N/A')
            count = cat.get('transaction_count', 0)
            lines.append(f"• {name} ({count} операций)")
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_categories: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_cat_add(message: types.Message):
    """Добавить новую категорию: /cat_add Продукты"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "Использование: /cat_add *название*\n"
            "Пример: /cat_add Продукты"
        )
        return
    
    name = args[1].strip()
    
    try:
        result = await api_create_category(message.from_user.id, name)
        await message.answer(f"✅ Категория создана: {name}")
    except Exception as e:
        logger.error(f"Error in cmd_cat_add: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_cat_delete(message: types.Message):
    """Удалить категорию: /cat_delete Продукты"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "Использование: /cat_delete *название*\n"
            "Пример: /cat_delete Продукты"
        )
        return
    
    name = args[1].strip()
    
    try:
        result = await api_delete_category(message.from_user.id, name)
        await message.answer(f"✅ Категория удалена: {name}")
    except Exception as e:
        logger.error(f"Error in cmd_cat_delete: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_cat_rename(message: types.Message):
    """Переименовать категорию: /cat_rename Продукты Еда"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "Использование: /cat_rename *старое* *новое*\n"
            "Пример: /cat_rename Продукты Еда"
        )
        return
    
    old_name = args[1].strip()
    new_name = args[2].strip()
    
    try:
        result = await api_rename_category(
            message.from_user.id,
            old_name,
            new_name
        )
        await message.answer(f"✅ Категория переименована: {old_name} → {new_name}")
    except Exception as e:
        logger.error(f"Error in cmd_cat_rename: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_cat_merge(message: types.Message):
    """Слить категории: /cat_merge Еда Продукты"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.answer(
            "Использование: /cat_merge *откуда* *куда*\n"
            "Пример: /cat_merge Еда Продукты\n"
            "(все операции из 'Еда' переместятся в 'Продукты')"
        )
        return
    
    source_name = args[1].strip()
    target_name = args[2].strip()
    
    try:
        result = await api_merge_categories(
            message.from_user.id,
            source_name,
            target_name
        )
        await message.answer(
            f"✅ Категории слиты: {source_name} → {target_name}"
        )
    except Exception as e:
        logger.error(f"Error in cmd_cat_merge: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
