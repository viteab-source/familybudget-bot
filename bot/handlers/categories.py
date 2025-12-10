"""
Обработчики управления категориями (через inline кнопки)
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

class CatAddStates(StatesGroup):
    waiting_for_name = State()


class CatRenameStates(StatesGroup):
    waiting_for_old_name = State()
    waiting_for_new_name = State()


class CatMergeStates(StatesGroup):
    waiting_for_source = State()
    waiting_for_target = State()


class CatDeleteStates(StatesGroup):
    waiting_for_name = State()


# ==========================================
# СПИСОК КАТЕГОРИЙ
# ==========================================

@router.callback_query(F.data == "cat_list")
async def cat_list_callback(callback: CallbackQuery):
    """Показать список категорий семьи"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Загружаю категории...")
    
    try:
        categories = await api.get_categories(telegram_id)
        
        if not categories:
            await callback.message.edit_text(
                "📂 Категорий пока нет.\n\n"
                "Нажми \"➕ Добавить\" чтобы создать."
            )
            await callback.answer()
            return
        
        text = "📂 <b>Категории:</b>\n\n"
        for cat in categories:
            text += f"• {cat['name']}\n"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# СОЗДАТЬ КАТЕГОРИЮ
# ==========================================

@router.callback_query(F.data == "cat_add")
async def cat_add_callback(callback: CallbackQuery, state: FSMContext):
    """Начало создания категории"""
    await callback.message.edit_text(
        "📝 <b>Создание категории</b>\n\n"
        "Введи название новой категории:",
        parse_mode="HTML"
    )
    await state.set_state(CatAddStates.waiting_for_name)
    await callback.answer()


@router.message(CatAddStates.waiting_for_name)
async def process_cat_add(message: types.Message, state: FSMContext):
    """Обработка создания категории"""
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    telegram_id = message.from_user.id
    
    try:
        await api.create_category(telegram_id, name)
        await message.answer(f"✅ Категория <b>{name}</b> создана!", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()


# ==========================================
# ПЕРЕИМЕНОВАТЬ КАТЕГОРИЮ
# ==========================================

@router.callback_query(F.data == "cat_rename")
async def cat_rename_callback(callback: CallbackQuery, state: FSMContext):
    """Начало переименования категории"""
    await callback.message.edit_text(
        "✏️ <b>Переименование категории</b>\n\n"
        "Введи текущее название категории:",
        parse_mode="HTML"
    )
    await state.set_state(CatRenameStates.waiting_for_old_name)
    await callback.answer()


@router.message(CatRenameStates.waiting_for_old_name)
async def process_cat_rename_old(message: types.Message, state: FSMContext):
    """Обработка старого названия"""
    old_name = message.text.strip()
    if not old_name:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    await state.update_data(old_name=old_name)
    await message.answer(f"📝 Введи новое название для категории <b>{old_name}</b>:", parse_mode="HTML")
    await state.set_state(CatRenameStates.waiting_for_new_name)


@router.message(CatRenameStates.waiting_for_new_name)
async def process_cat_rename_new(message: types.Message, state: FSMContext):
    """Обработка нового названия и переименование"""
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    data = await state.get_data()
    old_name = data["old_name"]
    
    telegram_id = message.from_user.id
    
    try:
        await api.rename_category(telegram_id, old_name, new_name)
        await message.answer(
            f"✅ Категория <b>{old_name}</b> переименована в <b>{new_name}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()


# ==========================================
# ОБЪЕДИНИТЬ КАТЕГОРИИ
# ==========================================

@router.callback_query(F.data == "cat_merge")
async def cat_merge_callback(callback: CallbackQuery, state: FSMContext):
    """Начало объединения категорий"""
    await callback.message.edit_text(
        "🔀 <b>Объединение категорий</b>\n\n"
        "Введи название <b>исходной</b> категории (будет удалена):",
        parse_mode="HTML"
    )
    await state.set_state(CatMergeStates.waiting_for_source)
    await callback.answer()


@router.message(CatMergeStates.waiting_for_source)
async def process_cat_merge_source(message: types.Message, state: FSMContext):
    """Обработка исходной категории"""
    source = message.text.strip()
    if not source:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    await state.update_data(source=source)
    await message.answer(
        f"📝 Введи название <b>целевой</b> категории (останется, все операции из <b>{source}</b> перейдут сюда):",
        parse_mode="HTML"
    )
    await state.set_state(CatMergeStates.waiting_for_target)


@router.message(CatMergeStates.waiting_for_target)
async def process_cat_merge_target(message: types.Message, state: FSMContext):
    """Обработка целевой категории и объединение"""
    target = message.text.strip()
    if not target:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    data = await state.get_data()
    source = data["source"]
    
    telegram_id = message.from_user.id
    
    try:
        await api.merge_categories(telegram_id, source, target)
        await message.answer(
            f"✅ Категории объединены:\n"
            f"<b>{source}</b> → <b>{target}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()


# ==========================================
# УДАЛИТЬ КАТЕГОРИЮ
# ==========================================

@router.callback_query(F.data == "cat_delete")
async def cat_delete_callback(callback: CallbackQuery, state: FSMContext):
    """Начало удаления категории"""
    await callback.message.edit_text(
        "🗑 <b>Удаление категории</b>\n\n"
        "⚠️ Можно удалить только пустую категорию (без операций).\n"
        "Если есть операции — используй \"🔗 Объединить\"\n\n"
        "Введи название категории:",
        parse_mode="HTML"
    )
    await state.set_state(CatDeleteStates.waiting_for_name)
    await callback.answer()


@router.message(CatDeleteStates.waiting_for_name)
async def process_cat_delete(message: types.Message, state: FSMContext):
    """Обработка удаления категории"""
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    telegram_id = message.from_user.id
    
    try:
        await api.delete_category(telegram_id, name)
        await message.answer(f"✅ Категория <b>{name}</b> удалена!", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()
