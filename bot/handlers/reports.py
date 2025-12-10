"""
Обработчики отчётов (через inline кнопки)
"""
from aiogram import types, Router, F
from aiogram.types import CallbackQuery, BufferedInputFile

from ..services.api_client import APIClient
from ..config import API_BASE_URL

router = Router()
api = APIClient(API_BASE_URL)


def format_amount(amount: float, currency: str = "RUB") -> str:
    """Форматирует сумму с разделителями."""
    return f"{amount:,.0f} {currency}".replace(",", " ")


# ==========================================
# ОТЧЁТ ПО РАСХОДАМ (вся семья)
# ==========================================

@router.callback_query(F.data == "report_all")
async def report_all_callback(callback: CallbackQuery):
    """Отчёт по расходам за 30 дней (вся семья)"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Формирую отчёт...")
    
    try:
        data = await api.get_summary_report(telegram_id, days=30)
        
        total = data.get("total_amount", 0)
        currency = data.get("currency", "RUB")
        by_category = data.get("by_category", [])
        
        if total == 0:
            await callback.message.edit_text("📊 Расходов за последние 30 дней нет.")
            await callback.answer()
            return
        
        text = f"📊 <b>Расходы за 30 дней (вся семья)</b>\n\n"
        text += f"Всего: <b>{format_amount(total, currency)}</b>\n\n"
        
        if by_category:
            text += "<b>По категориям:</b>\n"
            for cat in by_category:
                cat_name = cat.get("category") or "Без категории"
                cat_amount = cat.get("amount", 0)
                text += f"• {cat_name}: {format_amount(cat_amount, currency)}\n"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# ОТЧЁТ ПО РАСХОДАМ (только я)
# ==========================================

@router.callback_query(F.data == "report_me")
async def report_me_callback(callback: CallbackQuery):
    """Отчёт по моим расходам за 30 дней"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Формирую отчёт...")
    
    try:
        # Получаем свой user_id
        me_data = await api.get_me(telegram_id)
        user_id = me_data.get("user_id")
        
        # Запрашиваем отчёт только по себе
        data = await api.get_summary_report(telegram_id, days=30, user_id=user_id)
        
        total = data.get("total_amount", 0)
        currency = data.get("currency", "RUB")
        by_category = data.get("by_category", [])
        
        if total == 0:
            await callback.message.edit_text("📊 Твоих расходов за последние 30 дней нет.")
            await callback.answer()
            return
        
        text = f"📊 <b>Мои расходы за 30 дней</b>\n\n"
        text += f"Всего: <b>{format_amount(total, currency)}</b>\n\n"
        
        if by_category:
            text += "<b>По категориям:</b>\n"
            for cat in by_category:
                cat_name = cat.get("category") or "Без категории"
                cat_amount = cat.get("amount", 0)
                text += f"• {cat_name}: {format_amount(cat_amount, currency)}\n"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# БАЛАНС (вся семья)
# ==========================================

@router.callback_query(F.data == "balance_all")
async def balance_all_callback(callback: CallbackQuery):
    """Баланс за 30 дней (вся семья)"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Считаю баланс...")
    
    try:
        data = await api.get_balance_report(telegram_id, days=30)
        
        expenses = data.get("expenses_total", 0)
        incomes = data.get("incomes_total", 0)
        net = data.get("net", 0)
        currency = data.get("currency", "RUB")
        
        net_emoji = "📈" if net >= 0 else "📉"
        
        text = f"💰 <b>Баланс за 30 дней (вся семья)</b>\n\n"
        text += f"📤 Доходы: <b>{format_amount(incomes, currency)}</b>\n"
        text += f"📥 Расходы: <b>{format_amount(expenses, currency)}</b>\n\n"
        text += f"{net_emoji} Итог: <b>{format_amount(net, currency)}</b>"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# БАЛАНС (только я)
# ==========================================

@router.callback_query(F.data == "balance_me")
async def balance_me_callback(callback: CallbackQuery):
    """Мой баланс за 30 дней"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Считаю баланс...")
    
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
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# ОТЧЁТ ПО ЛЮДЯМ
# ==========================================

@router.callback_query(F.data == "report_members")
async def report_members_callback(callback: CallbackQuery):
    """Отчёт по людям: кто сколько потратил"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Формирую отчёт...")
    
    try:
        data = await api.get_members_report(telegram_id, days=30)
        
        members = data.get("members", [])
        currency = data.get("currency", "RUB")
        
        if not members:
            await callback.message.edit_text("👥 Расходов по людям за 30 дней нет.")
            await callback.answer()
            return
        
        text = f"👥 <b>Расходы по людям (30 дней)</b>\n\n"
        
        for m in members:
            name = m.get("name") or f"TG {m.get('telegram_id')}"
            amount = m.get("amount", 0)
            text += f"• <b>{name}</b>: {format_amount(amount, currency)}\n"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# ОТЧЁТ ПО МАГАЗИНАМ
# ==========================================

@router.callback_query(F.data == "report_shops")
async def report_shops_callback(callback: CallbackQuery):
    """Отчёт по магазинам"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("⏳ Формирую отчёт...")
    
    try:
        data = await api.get_shops_report(telegram_id, days=30)
        
        shops = data.get("shops", [])
        currency = data.get("currency", "RUB")
        
        if not shops:
            await callback.message.edit_text("🏪 Расходов по магазинам за 30 дней нет.")
            await callback.answer()
            return
        
        text = f"🏪 <b>Топ магазинов (30 дней)</b>\n\n"
        
        for shop in shops[:10]:  # Топ-10
            merchant = shop.get("merchant", "Неизвестно")
            amount = shop.get("amount", 0)
            text += f"• <b>{merchant}</b>: {format_amount(amount, currency)}\n"
        
        await callback.message.edit_text(text.strip(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()


# ==========================================
# ЭКСПОРТ В CSV
# ==========================================

@router.callback_query(F.data == "export_csv")
async def export_csv_callback(callback: CallbackQuery):
    """Экспорт транзакций в CSV за 30 дней"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text("📊 Генерирую CSV...")
    
    try:
        csv_data = await api.export_csv(telegram_id, days=30)
        
        # Отправляем файл
        file = BufferedInputFile(csv_data, filename="transactions_30d.csv")
        await callback.message.answer_document(file, caption="📊 Транзакции за 30 дней")
        
        await callback.message.edit_text("✅ CSV файл отправлен!")
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await callback.answer()
