"""
Команды для работы с бюджетами.
"""
from aiogram import types, Router
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

class BudgetSetStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_amount = State()


# ==========================================
# /budget_set — установить лимит бюджета
# ==========================================

@router.message(Command("budget_set"))
async def cmd_budget_set(message: types.Message, state: FSMContext):
    """Начало установки лимита бюджета."""
    await message.answer("📊 Введи название категории для бюджета:")
    await state.set_state(BudgetSetStates.waiting_for_category)


@router.message(BudgetSetStates.waiting_for_category)
async def process_budget_category(message: types.Message, state: FSMContext):
    """Обработка категории."""
    category = message.text.strip()
    if not category:
        await message.answer("❌ Категория не может быть пустой. Попробуй ещё раз:")
        return
    
    await state.update_data(category=category)
    await message.answer(f"💰 Введи лимит бюджета для категории <b>{category}</b> на месяц:", parse_mode="HTML")
    await state.set_state(BudgetSetStates.waiting_for_amount)


@router.message(BudgetSetStates.waiting_for_amount)
async def process_budget_amount(message: types.Message, state: FSMContext):
    """Обработка суммы лимита и установка бюджета."""
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


# ==========================================
# /budget_status — статус бюджетов
# ==========================================

@router.message(Command("budget_status"))
async def cmd_budget_status(message: types.Message):
    """Показать статус всех бюджетов."""
    telegram_id = message.from_user.id
    
    try:
        data = await api.get_budget_status(telegram_id)
        
        period = data.get("period", "")
        budgets = data.get("budgets", [])
        
        if not budgets:
            await message.answer(
                "📊 Бюджетов пока нет.\n\n"
                "Используй /budget_set чтобы установить лимиты по категориям."
            )
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
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
