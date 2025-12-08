"""
bot/handlers/profile.py — Команды для профиля, семьи, имён
"""

import asyncio
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import logger
from bot.api_client import (
    api_get_me,
    api_get_household,
    api_set_name,
    api_join_household,
    api_get_household_invite,
    api_rename_household,
    api_leave_household,
)
from bot.cache import pending_family_leave_confirmations, _clear_family_leave_confirmation
from bot.ui_helpers import format_amount


async def cmd_me(message: types.Message):
    """Показать профиль пользователя"""
    try:
        user = await api_get_me(message.from_user.id)
        
        text = f"""
👤 **Мой профиль**

Telegram ID: `{user.get('telegram_id')}`
Имя: {user.get('name') or 'Не установлено'}
Создан: {user.get('created_at', 'N/A')}
"""
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_me: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_setname(message: types.Message):
    """Установить имя пользователя"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("Использование: /setname *новое_имя*\nПример: /setname Иван")
        return
    
    new_name = args[1].strip()
    
    if len(new_name) > 50:
        await message.answer("❌ Имя слишком длинное (макс. 50 символов)")
        return
    
    try:
        result = await api_set_name(message.from_user.id, new_name)
        await message.answer(f"✅ Имя обновлено: {new_name}")
    except Exception as e:
        logger.error(f"Error in cmd_setname: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_family(message: types.Message):
    """Показать информацию о семье"""
    try:
        household = await api_get_household(message.from_user.id)
        
        members_text = "\n".join([
            f"• {m.get('name', 'N/A')} (ID: {m.get('id')})"
            for m in household.get('members', [])
        ])
        
        text = f"""
👨‍👩‍👧 **Информация о семье**

Название: {household.get('name', 'Не установлено')}
Участников: {len(household.get('members', []))}

**Члены семьи:**
{members_text or 'Нет членов'}

ID семьи: `{household.get('id')}`
Создана: {household.get('created_at', 'N/A')}
"""
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_family: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_family_invite(message: types.Message):
    """Получить код приглашения в семью"""
    try:
        result = await api_get_household_invite(message.from_user.id)
        code = result.get('invite_code', 'N/A')
        
        text = f"""
🎟️ **Код приглашения в семью**

Поделись этим кодом с членом семьи:

`{code}`

Они должны выполнить:
/family_join {code}
"""
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_family_invite: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_family_join(message: types.Message):
    """Присоединиться к семье по коду"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("Использование: /family_join *код*")
        return
    
    code = args[1].strip()
    
    try:
        result = await api_join_household(message.from_user.id, code)
        await message.answer(f"✅ Ты присоединился к семье: {result.get('name')}")
    except Exception as e:
        logger.error(f"Error in cmd_family_join: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_family_rename(message: types.Message):
    """Переименовать семью"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("Использование: /family_rename *новое_название*")
        return
    
    new_name = args[1].strip()
    
    try:
        result = await api_rename_household(message.from_user.id, new_name)
        await message.answer(f"✅ Семья переименована: {new_name}")
    except Exception as e:
        logger.error(f"Error in cmd_family_rename: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_family_leave(message: types.Message):
    """Начать процесс выхода из семьи (с подтверждением)"""
    user_id = message.from_user.id
    
    # Добавляем пользователя в очередь подтверждений
    pending_family_leave_confirmations.add(user_id)
    
    # Запускаем таск для автоочистки
    asyncio.create_task(_clear_family_leave_confirmation(user_id))
    
    # Показываем кнопку подтверждения
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, выйти из семьи",
                    callback_data="family_leave_confirm"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="family_leave_cancel"
                ),
            ]
        ]
    )
    
    await message.answer(
        "⚠️ Ты действительно хочешь выйти из семьи?\n\n"
        "Твои данные не удалятся, но ты больше не сможешь видеть данные семьи.",
        reply_markup=kb
    )
