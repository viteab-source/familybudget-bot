"""
bot/handlers/reports.py — Команды для отчётов
"""

from aiogram import types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from bot.config import logger
from bot.api_client import (
    api_get_summary_report,
    api_get_balance_report,
    api_get_members_report,
    api_report_shops,
    api_export_csv,
)
from bot.ui_helpers import format_amount


async def cmd_report_summary(message: types.Message):
    """Сводка расходов/доходов за последние 14 дней"""
    args = message.text.split()
    days = 14
    
    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass
    
    try:
        report = await api_get_summary_report(message.from_user.id, days=days)
        
        lines = [
            f"📊 **Сводка за {days} дней**",
            "",
            f"💰 Расходы: {format_amount(report.get('total_expenses', 0), 'RUB')}",
            f"📈 Доходы: {format_amount(report.get('total_income', 0), 'RUB')}",
            f"📉 Баланс: {format_amount(report.get('net', 0), 'RUB')}",
        ]
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_report_summary: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_report_balance(message: types.Message):
    """Баланс по категориям"""
    args = message.text.split()
    days = 30
    
    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass
    
    try:
        report = await api_get_balance_report(message.from_user.id, days=days)
        
        lines = [f"📊 **Баланс по категориям за {days} дней**", ""]
        
        for cat_name, amount in (report.get('categories', {}) or {}).items():
            lines.append(f"• {cat_name}: {format_amount(amount, 'RUB')}")
        
        if not lines or len(lines) <= 2:
            await message.answer(f"📂 Нет данных за {days} дней")
            return
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_report_balance: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_report_members(message: types.Message):
    """Расходы по членам семьи"""
    args = message.text.split()
    days = 30
    
    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass
    
    try:
        report = await api_get_members_report(message.from_user.id, days=days)
        
        lines = [f"👥 **Расходы по членам за {days} дней**", ""]
        
        for member_name, amount in (report.get('members', {}) or {}).items():
            lines.append(f"• {member_name}: {format_amount(amount, 'RUB')}")
        
        if not lines or len(lines) <= 2:
            await message.answer(f"👥 Нет данных за {days} дней")
            return
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_report_members: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_report_shops(message: types.Message):
    """Расходы по магазинам"""
    args = message.text.split()
    days = 30
    
    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass
    
    try:
        report = await api_report_shops(message.from_user.id, days=days)
        
        lines = [f"🏪 **Расходы по магазинам за {days} дней**", ""]
        
        for shop_name, amount in (report.get('shops', {}) or {}).items():
            lines.append(f"• {shop_name}: {format_amount(amount, 'RUB')}")
        
        if not lines or len(lines) <= 2:
            await message.answer(f"🏪 Нет данных за {days} дней")
            return
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_report_shops: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")


async def cmd_report_export(message: types.Message):
    """Экспортировать отчёт в CSV"""
    args = message.text.split()
    days = 30
    
    if len(args) > 1:
        try:
            days = int(args[1])
        except ValueError:
            pass
    
    try:
        # Получаем CSV контент
        csv_data = await api_export_csv(message.from_user.id, days=days)
        
        # Создаём файл
        file = BufferedInputFile(
            file=csv_data,
            filename=f"budget_export_{days}d.csv"
        )
        
        await message.answer_document(
            file,
            caption=f"📊 Экспорт за {days} дней"
        )
    except Exception as e:
        logger.error(f"Error in cmd_report_export: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
