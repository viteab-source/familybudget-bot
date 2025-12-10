"""
Обработчики настроек профиля и семьи (через inline кнопки)
"""
from aiogram import types, Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..services.api_client import APIClient
from ..config import API_BASE_URL

router = Router()
api = APIClient(API_BASE_URL)


# ==========================================
# FSM States
# ==========================================

class SetNameStates(StatesGroup):
    waiting_for_name = State()


class FamilyJoinStates(StatesGroup):
    waiting_for_code = State()


class FamilyRenameStates(StatesGroup):
    waiting_for_name = State()


# ==========================================
# МОЙ ПРОФИЛЬ
# ==========================================

@router.callback_query(F.data == "settings_me")
async def settings_me_callback(callback: CallbackQuery):
    """Показать информацию о профиле"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Загружаю информацию...")
    
    try:
        data = await api.get_me(telegram_id)
        
        name = data.get("name") or "Не задано"
        household_name = data.get("household_name", "Семья")
        currency = data.get("currency", "RUB")
        role = data.get("role", "member")
        members = data.get("members", [])

        role_emoji = {"owner": "👑", "admin": "⚙️", "member": "👤"}.get(role, "👤")

        text = f"""👤 <b>Твой профиль</b>

Имя: <b>{name}</b>
Telegram ID: <code>{telegram_id}</code>

🏠 <b>Семья: {household_name}</b>
Роль: {role_emoji} {role}
Валюта: {currency}

👥 <b>Участники ({len(members)}):</b>
"""
        for m in members:
            m_name = m.get("name") or f"TG {m.get('telegram_id')}"
            m_role = m.get("role", "member")
            m_emoji = {"owner": "👑", "admin": "⚙️", "member": "👤"}.get(m_role, "👤")
            text += f"{m_emoji} {m_name}\n"

        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# УСТАНОВИТЬ ИМЯ
# ==========================================

@router.callback_query(F.data == "settings_name")
async def settings_name_callback(callback: CallbackQuery, state: FSMContext):
    """Начало процесса установки имени"""
    await callback.message.edit_text(
        "👤 <b>Установить имя</b>\n\n"
        "Напиши своё имя (как оно будет видно в семье):",
        parse_mode="HTML"
    )
    await state.set_state(SetNameStates.waiting_for_name)
    await callback.answer()


@router.message(SetNameStates.waiting_for_name)
async def process_setname(message: types.Message, state: FSMContext):
    """Обработка ввода имени"""
    name = message.text.strip()
    if not name:
        await message.answer("❌ Имя не может быть пустым. Попробуй ещё раз:")
        return

    telegram_id = message.from_user.id

    try:
        await api.set_user_name(telegram_id, name)
        await message.answer(f"✅ Твоё имя обновлено: <b>{name}</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


# ==========================================
# ИНФОРМАЦИЯ О СЕМЬЕ
# ==========================================

@router.callback_query(F.data == "family_info")
async def family_info_callback(callback: CallbackQuery):
    """Показать информацию о семье"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Загружаю информацию...")
    
    try:
        data = await api.get_household(telegram_id)
        
        household_name = data.get("name", "Семья")
        currency = data.get("currency", "RUB")
        members = data.get("members", [])

        text = f"""🏠 <b>{household_name}</b>
Валюта: {currency}

👥 <b>Участники ({len(members)}):</b>
"""
        for m in members:
            m_name = m.get("name") or f"TG {m.get('telegram_id')}"
            m_role = m.get("role", "member")
            m_emoji = {"owner": "👑", "admin": "⚙️", "member": "👤"}.get(m_role, "👤")
            text += f"{m_emoji} {m_name}\n"

        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# КОД ПРИГЛАШЕНИЯ
# ==========================================

@router.callback_query(F.data == "family_invite")
async def family_invite_callback(callback: CallbackQuery):
    """Создать код приглашения в семью"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Генерирую код...")
    
    try:
        data = await api.get_household_invite(telegram_id)
        code = data.get("code")
        
        text = f"""🎫 <b>Код приглашения в семью:</b>

<code>{code}</code>

Отправь этот код другому человеку.
Он должен нажать \"➕ Присоединиться\" в меню Семьи.
"""
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# ПРИСОЕДИНИТЬСЯ К СЕМЬЕ
# ==========================================

@router.callback_query(F.data == "family_join")
async def family_join_callback(callback: CallbackQuery, state: FSMContext):
    """Начало процесса присоединения к семье"""
    await callback.message.edit_text(
        "🔗 <b>Присоединиться к семье</b>\n\n"
        "Введи код приглашения:",
        parse_mode="HTML"
    )
    await state.set_state(FamilyJoinStates.waiting_for_code)
    await callback.answer()


@router.message(FamilyJoinStates.waiting_for_code)
async def process_family_join(message: types.Message, state: FSMContext):
    """Обработка кода приглашения"""
    code = message.text.strip()
    if not code:
        await message.answer("❌ Код не может быть пустым. Попробуй ещё раз:")
        return

    telegram_id = message.from_user.id

    try:
        data = await api.join_household(telegram_id, code)
        household_name = data.get("name", "Семья")
        await message.answer(f"✅ Ты присоединился к семье <b>{household_name}</b>!", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


# ==========================================
# ПЕРЕИМЕНОВАТЬ СЕМЬЮ
# ==========================================

@router.callback_query(F.data == "family_rename")
async def family_rename_callback(callback: CallbackQuery, state: FSMContext):
    """Начало процесса переименования семьи"""
    await callback.message.edit_text(
        "✏️ <b>Переименовать семью</b>\n\n"
        "Введи новое название семьи:",
        parse_mode="HTML"
    )
    await state.set_state(FamilyRenameStates.waiting_for_name)
    await callback.answer()


@router.message(FamilyRenameStates.waiting_for_name)
async def process_family_rename(message: types.Message, state: FSMContext):
    """Обработка нового названия"""
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return

    telegram_id = message.from_user.id

    try:
        await api.rename_household(telegram_id, name)
        await message.answer(f"✅ Семья переименована в <b>{name}</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

    await state.clear()


# ==========================================
# ВЫЙТИ ИЗ СЕМЬИ
# ==========================================

@router.callback_query(F.data == "family_leave")
async def family_leave_callback(callback: CallbackQuery):
    """Выйти из текущей семьи"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Выходим из семьи...")
    
    try:
        data = await api.leave_household(telegram_id)
        msg = data.get("message", "Ты вышел из семьи")
        await callback.message.edit_text(f"✅ {msg}")
        await callback.answer()
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()
