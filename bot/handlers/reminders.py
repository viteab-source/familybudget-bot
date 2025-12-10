"""
Обработчики напоминаний (через inline кнопки)
"""
from datetime import datetime
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

class RemindAddStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_amount = State()
    waiting_for_interval = State()


# ==========================================
# СПИСОК НАПОМИНАНИЙ
# ==========================================

@router.callback_query(F.data == "remind_list")
async def remind_list_callback(callback: CallbackQuery):
    """Показать список активных напоминаний"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Загружаю напоминания...")
    
    try:
        reminders = await api.list_reminders(telegram_id)
        
        if not reminders:
            await callback.message.edit_text(
                "🔔 Активных напоминаний нет.\n\n"
                "Нажми \"➕ Добавить\" чтобы создать."
            )
            await callback.answer()
            return
        
        text = "🔔 <b>Активные напоминания:</b>\n\n"
        
        for r in reminders:
            title = r.get("title", "Без названия")
            amount = r.get("amount")
            interval = r.get("interval_days")
            next_run = r.get("next_run_at")
            
            text += f"📝 <b>{title}</b>\n"
            if amount:
                text += f"💰 {amount:,.0f} RUB\n"
            if interval:
                text += f"📅 Каждые {interval} дн.\n"
            if next_run:
                try:
                    dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
                    text += f"⏰ Следующее: {dt.strftime('%d.%m.%Y')}\n"
                except:
                    pass
            text += "\n"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# НАПОМИНАНИЯ НА СЕГОДНЯ
# ==========================================

@router.callback_query(F.data == "remind_due")
async def remind_due_callback(callback: CallbackQuery):
    """Показать напоминания на сегодня"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Проверяю напоминания...")
    
    try:
        reminders = await api.get_due_reminders(telegram_id)
        
        if not reminders:
            await callback.message.edit_text("✅ На сегодня напоминаний нет!")
            await callback.answer()
            return
        
        text = "🔔 <b>Напоминания на сегодня:</b>\n\n"
        
        for r in reminders:
            rid = r.get("id")
            title = r.get("title", "Без названия")
            amount = r.get("amount")
            
            text += f"📝 <b>{title}</b>\n"
            if amount:
                text += f"💰 {amount:,.0f} RUB\n"
            text += f"ID: <code>{rid}</code>\n\n"
        
        text += "\n💡 Функция \"Отметить как оплаченное\" скоро будет добавлена"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# СОЗДАТЬ НАПОМИНАНИЕ
# ==========================================

@router.callback_query(F.data == "remind_add")
async def remind_add_callback(callback: CallbackQuery, state: FSMContext):
    """Начало создания напоминания"""
    await callback.message.edit_text(
        "🔔 <b>Создание напоминания</b>\n\n"
        "Введи название (например: Коммуналка):",
        parse_mode="HTML"
    )
    await state.set_state(RemindAddStates.waiting_for_title)
    await callback.answer()


@router.message(RemindAddStates.waiting_for_title)
async def process_remind_title(message: types.Message, state: FSMContext):
    """Обработка названия"""
    title = message.text.strip()
    if not title:
        await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
        return
    
    await state.update_data(title=title)
    await message.answer("💰 Введи сумму (или '-' если без суммы):")
    await state.set_state(RemindAddStates.waiting_for_amount)


@router.message(RemindAddStates.waiting_for_amount)
async def process_remind_amount(message: types.Message, state: FSMContext):
    """Обработка суммы"""
    text = message.text.strip()
    
    amount = None
    if text != "-":
        try:
            amount = float(text.replace(",", "."))
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await message.answer("❌ Введи корректную сумму или '-' для пропуска:")
            return
    
    await state.update_data(amount=amount)
    await message.answer(
        "📅 Введи интервал в днях (например: 30 для ежемесячного)\n"
        "Или '-' для разового напоминания:"
    )
    await state.set_state(RemindAddStates.waiting_for_interval)


@router.message(RemindAddStates.waiting_for_interval)
async def process_remind_interval(message: types.Message, state: FSMContext):
    """Обработка интервала и создание напоминания"""
    text = message.text.strip()
    
    interval_days = None
    if text != "-":
        try:
            interval_days = int(text)
            if interval_days <= 0:
                raise ValueError()
        except ValueError:
            await message.answer("❌ Введи корректное число дней или '-' для разового:")
            return
    
    data = await state.get_data()
    title = data["title"]
    amount = data.get("amount")
    
    telegram_id = message.from_user.id
    
    try:
        reminder = await api.create_reminder(telegram_id, title, amount, interval_days)
        
        text = f"✅ Напоминание создано:\n\n"
        text += f"📝 <b>{title}</b>\n"
        if amount:
            text += f"💰 Сумма: {amount:,.0f} RUB\n"
        if interval_days:
            text += f"📅 Повторять каждые {interval_days} дн."
        else:
            text += f"📅 Разовое"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()
