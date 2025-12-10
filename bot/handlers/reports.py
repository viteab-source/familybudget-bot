"""
Команды для отчётов.
"""
from aiogram import types, Router
from aiogram.filters import Command

from ..services.api_client import APIClient
from ..config import API_BASE_URL

router = Router()
api = APIClient(API_BASE_URL)


def format_amount(amount: float, currency: str = "RUB") -> str:
    """Форматирует сумму с разделителями."""
    return f"{amount:,.0f} {currency}".replace(",", " ")


# ==========================================
# /report — расходы за 14 дней (вся семья)
# ==========================================

@router.message(Command("report"))
async def cmd_report(message: types.Message):
    """Отчёт по расходам за 14 дней."""
    telegram_id = message.from_user.id
    
    try:
        data = await api.get_summary_report(telegram_id, days=14)
        
        total = data.get("total_amount", 0)
        currency = data.get("currency", "RUB")
        by_category = data.get("by_category", [])
        
        if total == 0:
            await message.answer("📊 Расходов за последние 14 дней нет.")
            return
        
        text = f"📊 <b>Расходы за 14 дней</b>\n\n"
        text += f"Всего: <b>{format_amount(total, currency)}</b>\n\n"
        
        if by_category:
            text += "<b>По категориям:</b>\n"
            for cat in by_category:
                cat_name = cat.get("category") or "Без категории"
                cat_amount = cat.get("amount", 0)
                text += f"• {cat_name}: {format_amount(cat_amount, currency)}\n"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /report_me — расходы за 14 дней (только я)
# ==========================================

@router.message(Command("report_me"))
async def cmd_report_me(message: types.Message):
    """Отчёт по моим расходам за 14 дней."""
    telegram_id = message.from_user.id
    
    try:
        # Сначала получаем свой user_id
        me_data = await api.get_me(telegram_id)
        user_id = me_data.get("user_id")
        
        # Теперь запрашиваем отчёт только по себе
        data = await api.get_summary_report(telegram_id, days=14, user_id=user_id)
        
        total = data.get("total_amount", 0)
        currency = data.get("currency", "RUB")
        by_category = data.get("by_category", [])
        
        if total == 0:
            await message.answer("📊 Твоих расходов за последние 14 дней нет.")
            return
        
        text = f"📊 <b>Мои расходы за 14 дней</b>\n\n"
        text += f"Всего: <b>{format_amount(total, currency)}</b>\n\n"
        
        if by_category:
            text += "<b>По категориям:</b>\n"
            for cat in by_category:
                cat_name = cat.get("category") or "Без категории"
                cat_amount = cat.get("amount", 0)
                text += f"• {cat_name}: {format_amount(cat_amount, currency)}\n"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /balance — баланс за 30 дней (вся семья)
# ==========================================

@router.message(Command("balance"))
async def cmd_balance(message: types.Message):
    """Баланс за 30 дней."""
    telegram_id = message.from_user.id
    
    try:
        data = await api.get_balance_report(telegram_id, days=30)
        
        expenses = data.get("expenses_total", 0)
        incomes = data.get("incomes_total", 0)
        net = data.get("net", 0)
        currency = data.get("currency", "RUB")
        
        net_emoji = "📈" if net >= 0 else "📉"
        
        text = f"💰 <b>Баланс за 30 дней</b>\n\n"
        text += f"📤 Доходы: <b>{format_amount(incomes, currency)}</b>\n"
        text += f"📥 Расходы: <b>{format_amount(expenses, currency)}</b>\n\n"
        text += f"{net_emoji} Итог: <b>{format_amount(net, currency)}</b>"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /balance_me — баланс за 30 дней (только я)
# ==========================================

@router.message(Command("balance_me"))
async def cmd_balance_me(message: types.Message):
    """Мой баланс за 30 дней."""
    telegram_id = message.from_user.id
    
    try:
        # Получаем свой user_id
        me_data = await api.get_me(telegram_id)
        user_id = me_data.get("user_id")
        
        # Запрашиваем баланс только по себе
        data = await api.get_balance_report(telegram_id, days=30, user_id=user_id)
        
        expenses = data.get("expenses_total", 0)
        incomes = data.get("incomes_total", 0)
        net = data.get("net", 0)
        currency = data.get("currency", "RUB")
        
        net_emoji = "📈" if net >= 0 else "📉"
        
        text = f"💰 <b>Мой баланс за 30 дней</b>\n\n"
        text += f"📤 Доходы: <b>{format_amount(incomes, currency)}</b>\n"
        text += f"📥 Расходы: <b>{format_amount(expenses, currency)}</b>\n\n"
        text += f"{net_emoji} Итог: <b>{format_amount(net, currency)}</b>"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /report_members — кто сколько потратил
# ==========================================

@router.message(Command("report_members"))
async def cmd_report_members(message: types.Message):
    """Отчёт по людям: кто сколько потратил."""
    telegram_id = message.from_user.id
    
    try:
        data = await api.get_members_report(telegram_id, days=30)
        
        members = data.get("members", [])
        currency = data.get("currency", "RUB")
        
        if not members:
            await message.answer("👥 Расходов по людям за 30 дней нет.")
            return
        
        text = f"👥 <b>Расходы по людям (30 дней)</b>\n\n"
        
        for m in members:
            name = m.get("name") or f"TG {m.get('telegram_id')}"
            amount = m.get("amount", 0)
            text += f"• <b>{name}</b>: {format_amount(amount, currency)}\n"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /report_shops — топ магазинов
# ==========================================

@router.message(Command("report_shops"))
async def cmd_report_shops(message: types.Message):
    """Отчёт по магазинам."""
    telegram_id = message.from_user.id
    
    try:
        data = await api.get_shops_report(telegram_id, days=30)
        
        shops = data.get("shops", [])
        currency = data.get("currency", "RUB")
        
        if not shops:
            await message.answer("🏪 Расходов по магазинам за 30 дней нет.")
            return
        
        text = f"🏪 <b>Топ магазинов (30 дней)</b>\n\n"
        
        for shop in shops[:10]:  # Топ-10
            merchant = shop.get("merchant", "Неизвестно")
            amount = shop.get("amount", 0)
            text += f"• <b>{merchant}</b>: {format_amount(amount, currency)}\n"
        
        await message.answer(text.strip(), parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ==========================================
# /export_csv — экспорт транзакций в CSV
# ==========================================

@router.message(Command("export_csv"))
async def cmd_export_csv(message: types.Message):
    """Экспорт транзакций в CSV за 30 дней."""
    telegram_id = message.from_user.id
    
    processing_msg = await message.answer("📊 Генерирую CSV...")
    
    try:
        csv_data = await api.export_csv(telegram_id, days=30)
        
        # Отправляем файл
        file = types.BufferedInputFile(csv_data, filename="transactions_30d.csv")
        await message.answer_document(file, caption="📊 Транзакции за 30 дней")
        
        await processing_msg.delete()
        
    except Exception as e:
        await processing_msg.delete()
        await message.answer(f"❌ Ошибка: {e}")
