"""
Обработчики управления бюджетами (через inline кнопки)
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

class BudgetSetStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_amount = State()


# ==========================================
# СТАТУС БЮДЖЕТОВ
# ==========================================

@router.callback_query(F.data == "budget_status")
async def budget_status_callback(callback: CallbackQuery):
    """Показать статус всех бюджетов"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Загружаю статус бюджетов...")
    
    try:
        data = await api.get_budget_status(telegram_id)
        
        period = data.get("period", "")
        budgets = data.get("budgets", [])
        
        if not budgets:
            await callback.message.edit_text(
                "📊 Бюджетов пока нет.\n\n"
                "Нажми \"💵 Установить лимит\" чтобы создать."
            )
            await callback.answer()
            return
        
        text = f"📊 <b>Статус бюджетов ({period})</b>\n\n"
        
        for b in budgets:
            category = b.get("category", "Без названия")
            limit = b.get("limit", 0)
            spent = b.get("spent", 0)
            percent = b.get("percent", 0)
            currency = b.get("currency", "RUB")
            
            # Эмодзи в зависимости от процента
            if percent >= 100:
                emoji = "🔴"
            elif percent >= 80:
                emoji = "🟡"
            else:
                emoji = "🟢"
            
            text += (
                f"{emoji} <b>{category}</b>\n"
                f"Потрачено: {spent:,.0f} / {limit:,.0f} {currency} ({percent}%)\n\n"
            )
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# УСТАНОВИТЬ ЛИМИТ БЮДЖЕТА
# ==========================================

@router.callback_query(F.data == "budget_set")
async def budget_set_callback(callback: CallbackQuery, state: FSMContext):
    """Начало установки лимита бюджета"""
    await callback.message.edit_text(
        "💵 <b>Установить лимит бюджета</b>\n\n"
        "Введи название категории для бюджета:",
        parse_mode="HTML"
    )
    await state.set_state(BudgetSetStates.waiting_for_category)
    await callback.answer()


@router.message(BudgetSetStates.waiting_for_category)
async def process_budget_category(message: types.Message, state: FSMContext):
    """Обработка категории"""
    category = message.text.strip()
    if not category:
        await message.answer("❌ Категория не может быть пустой. Попробуй ещё раз:")
        return
    
    await state.update_data(category=category)
    await message.answer(f"💰 Введи лимит бюджета для категории <b>{category}</b> на месяц:", parse_mode="HTML")
    await state.set_state(BudgetSetStates.waiting_for_amount)


@router.message(BudgetSetStates.waiting_for_amount)
async def process_budget_amount(message: types.Message, state: FSMContext):
    """Обработка суммы лимита и установка бюджета"""
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введи корректную сумму (например: 50000):")
        return
    
    data = await state.get_data()
    category = data["category"]
    
    telegram_id = message.from_user.id
    
    try:
        result = await api.set_budget(telegram_id, category, amount)
        
        await message.answer(
            f"✅ Бюджет установлен:\n"
            f"Категория: <b>{category}</b>\n"
            f"Лимит: <b>{amount:,.0f} RUB</b> в месяц",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()
