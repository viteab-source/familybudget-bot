"""
Команды для работы с пользователем и семьёй.
"""
from aiogram import types, Router, F
from aiogram.filters import Command
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
# /setname — задать имя пользователя
# ==========================================

@router.message(Command("setname"))
async def cmd_setname(message: types.Message, state: FSMContext):
    """Начало процесса установки имени."""
    await message.answer("Напиши своё имя (как оно будет видно в семье):")
    await state.set_state(SetNameStates.waiting_for_name)


@router.message(SetNameStates.waiting_for_name)
async def process_setname(message: types.Message, state: FSMContext):
    """Обработка ввода имени."""
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
# /me — информация о пользователе
# ==========================================

@router.message(Command("me"))
async def cmd_me(message: types.Message):
    """Показать информацию о пользователе и его семье."""
    telegram_id = message.from_user.id

    try:
        data = await api.get_me(telegram_id)
        
        name = data.get("name") or "Не задано"
        household_name = data.get("household_name", "Семья")
        currency = data.get("currency", "RUB")
        role = data.get("role", "member")
        members = data.get("members", [])

        role_emoji = {"owner": "👑", "admin": "⚙️", "member": "👤"}.get(role, "👤")

        text = f"""
👤 <b>Твой профиль</b>

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

        await message.answer(text.strip(), parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /family — информация о семье
# ==========================================

@router.message(Command("family"))
async def cmd_family(message: types.Message):
    """Показать информацию о семье."""
    telegram_id = message.from_user.id

    try:
        data = await api.get_household(telegram_id)
        
        household_name = data.get("name", "Семья")
        currency = data.get("currency", "RUB")
        members = data.get("members", [])

        text = f"""
🏠 <b>{household_name}</b>
Валюта: {currency}

👥 <b>Участники ({len(members)}):</b>
"""
        for m in members:
            m_name = m.get("name") or f"TG {m.get('telegram_id')}"
            m_role = m.get("role", "member")
            m_emoji = {"owner": "👑", "admin": "⚙️", "member": "👤"}.get(m_role, "👤")
            text += f"{m_emoji} {m_name}\n"

        await message.answer(text.strip(), parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /family_invite — пригласить в семью
# ==========================================

@router.message(Command("family_invite"))
async def cmd_family_invite(message: types.Message):
    """Создать код приглашения в семью."""
    telegram_id = message.from_user.id

    try:
        data = await api.get_household_invite(telegram_id)
        code = data.get("code")
        
        text = f"""
🎫 <b>Код приглашения в семью:</b>

<code>{code}</code>

Отправь этот код другому человеку.
Он должен использовать команду:
/family_join
"""
        await message.answer(text.strip(), parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /family_join — присоединиться к семье
# ==========================================

@router.message(Command("family_join"))
async def cmd_family_join(message: types.Message, state: FSMContext):
    """Начало процесса присоединения к семье."""
    await message.answer("Введи код приглашения:")
    await state.set_state(FamilyJoinStates.waiting_for_code)


@router.message(FamilyJoinStates.waiting_for_code)
async def process_family_join(message: types.Message, state: FSMContext):
    """Обработка кода приглашения."""
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
# /family_rename — переименовать семью
# ==========================================

@router.message(Command("family_rename"))
async def cmd_family_rename(message: types.Message, state: FSMContext):
    """Начало процесса переименования семьи."""
    await message.answer("Введи новое название семьи:")
    await state.set_state(FamilyRenameStates.waiting_for_name)


@router.message(FamilyRenameStates.waiting_for_name)
async def process_family_rename(message: types.Message, state: FSMContext):
    """Обработка нового названия."""
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
# /family_leave — выйти из семьи
# ==========================================

@router.message(Command("family_leave"))
async def cmd_family_leave(message: types.Message):
    """Выйти из текущей семьи."""
    telegram_id = message.from_user.id

    try:
        data = await api.leave_household(telegram_id)
        msg = data.get("message", "Ты вышел из семьи")
        await message.answer(f"✅ {msg}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
