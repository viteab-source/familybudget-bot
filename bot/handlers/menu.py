"""
Обработчики главного меню (кнопки из persistent keyboard)
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.keyboards.inline import (
    get_reports_menu,
    get_settings_menu,
    get_reminders_menu,
    get_family_menu,
    get_categories_menu,
    get_budgets_menu
)

logger = logging.getLogger(__name__)
router = Router()


# === ГЛАВНЫЕ КНОПКИ ===

@router.message(F.text == "📊 Отчёты")
async def reports_button(message: Message):
    """Кнопка Отчёты - показать меню отчётов"""
    text = (
        "📊 <b>Отчёты и статистика</b>\n\n"
        "Выберите что посмотреть:"
    )
    await message.answer(
        text,
        reply_markup=get_reports_menu(),
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} opened reports menu")


@router.message(F.text == "⚙️ Настройки")
async def settings_button(message: Message):
    """Кнопка Настройки - показать меню настроек"""
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        "Что хотите настроить?"
    )
    await message.answer(
        text,
        reply_markup=get_settings_menu(),
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} opened settings menu")


@router.message(F.text == "🔔 Напоминания")
async def reminders_button(message: Message):
    """Кнопка Напоминания - показать меню напоминаний"""
    text = (
        "🔔 <b>Напоминания</b>\n\n"
        "Управление напоминаниями о платежах:"
    )
    await message.answer(
        text,
        reply_markup=get_reminders_menu(),
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} opened reminders menu")


# === НАВИГАЦИЯ МЕЖДУ ПОДМЕНЮ НАСТРОЕК ===

@router.callback_query(F.data == "settings_family")
async def settings_family_callback(callback: CallbackQuery):
    """Открыть подменю Семья"""
    text = (
        "👨‍👩‍👧 <b>Управление семьёй</b>\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_family_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "settings_categories")
async def settings_categories_callback(callback: CallbackQuery):
    """Открыть подменю Категории"""
    text = (
        "🏷 <b>Управление категориями</b>\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_categories_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "settings_budgets")
async def settings_budgets_callback(callback: CallbackQuery):
    """Открыть подменю Бюджеты"""
    text = (
        "💵 <b>Управление бюджетами</b>\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_budgets_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "back_settings")
async def back_to_settings(callback: CallbackQuery):
    """Возврат в главное меню настроек"""
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        "Что хотите настроить?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_settings_menu(),
        parse_mode="HTML"
    )
    await callback.answer()
