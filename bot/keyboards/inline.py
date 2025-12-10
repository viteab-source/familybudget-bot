"""Inline клавиатуры для подменю бота"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# === ОТЧЁТЫ ===

def get_reports_menu() -> InlineKeyboardMarkup:
    """Меню отчётов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 За месяц (вся семья)", callback_data="report_all")],
        [InlineKeyboardButton(text="👤 Мои расходы", callback_data="report_me")],
        [InlineKeyboardButton(text="💰 Баланс (вся семья)", callback_data="balance_all")],
        [InlineKeyboardButton(text="💵 Мой баланс", callback_data="balance_me")],
        [InlineKeyboardButton(text="👨‍👩‍👧 По людям", callback_data="report_members")],
        [InlineKeyboardButton(text="🏪 По магазинам", callback_data="report_shops")],
        [InlineKeyboardButton(text="📥 Скачать CSV", callback_data="export_csv")],
    ])
    return keyboard


# === НАСТРОЙКИ ===

def get_settings_menu() -> InlineKeyboardMarkup:
    """Главное меню настроек"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Моё имя", callback_data="settings_name")],
        [InlineKeyboardButton(text="ℹ️ Мой профиль", callback_data="settings_me")],
        [InlineKeyboardButton(text="👨‍👩‍👧 Семья", callback_data="settings_family")],
        [InlineKeyboardButton(text="🏷 Категории", callback_data="settings_categories")],
        [InlineKeyboardButton(text="💵 Бюджеты", callback_data="settings_budgets")],
    ])
    return keyboard


def get_family_menu() -> InlineKeyboardMarkup:
    """Подменю управления семьёй"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Инфо о семье", callback_data="family_info")],
        [InlineKeyboardButton(text="🔗 Код приглашения", callback_data="family_invite")],
        [InlineKeyboardButton(text="➕ Присоединиться", callback_data="family_join")],
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data="family_rename")],
        [InlineKeyboardButton(text="🚪 Выйти из семьи", callback_data="family_leave")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_settings")],
    ])
    return keyboard


def get_categories_menu() -> InlineKeyboardMarkup:
    """Подменю управления категориями"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список категорий", callback_data="cat_list")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="cat_add")],
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data="cat_rename")],
        [InlineKeyboardButton(text="🔗 Объединить", callback_data="cat_merge")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="cat_delete")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_settings")],
    ])
    return keyboard


def get_budgets_menu() -> InlineKeyboardMarkup:
    """Подменю управления бюджетами"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статус бюджетов", callback_data="budget_status")],
        [InlineKeyboardButton(text="💵 Установить лимит", callback_data="budget_set")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_settings")],
    ])
    return keyboard


# === НАПОМИНАНИЯ ===

def get_reminders_menu() -> InlineKeyboardMarkup:
    """Меню напоминаний"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Все напоминания", callback_data="remind_list")],
        [InlineKeyboardButton(text="📅 На сегодня", callback_data="remind_due")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="remind_add")],
    ])
    return keyboard


# === ВСПОМОГАТЕЛЬНЫЕ ===

def get_back_button(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    """Кнопка Назад"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад", callback_data=callback_data)],
    ])
    return keyboard
