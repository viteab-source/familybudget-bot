"""
bot/handlers/__init__.py — Регистрация всех handlers (ИСПРАВЛЕНО!)

ВАЖНО: Используем F фильтры вместо декораторов!
"""

from aiogram import Dispatcher, types, F
from aiogram.filters import CommandStart, Command

# Импортируем функции-обработчики из каждого модуля
from . import start_help, profile, transactions, ai_input, reports, categories, reminders, budgets, callbacks


def setup(dp: Dispatcher):
    """
    Подключаем все обработчики к диспетчеру.
    Вызывается из bot/main.py при инициализации.
    """
    
    # ===== START & HELP =====
    dp.message.register(start_help.cmd_start, CommandStart())
    dp.message.register(start_help.cmd_help, Command("help"))
    
    # ===== PROFILE =====
    dp.message.register(profile.cmd_me, Command("me"))
    dp.message.register(profile.cmd_family, Command("family"))
    dp.message.register(profile.cmd_setname, Command("setname"))
    dp.message.register(profile.cmd_family_join, Command("family_join"))
    dp.message.register(profile.cmd_family_leave, Command("family_leave"))
    dp.message.register(profile.cmd_family_rename, Command("family_rename"))
    dp.message.register(profile.cmd_family_invite, Command("family_invite"))
    
    # ===== TRANSACTIONS =====
    dp.message.register(transactions.cmd_add, Command("add"))
    dp.message.register(transactions.cmd_income, Command("income"))
    dp.message.register(transactions.cmd_last, Command("last"))
    dp.message.register(transactions.cmd_del_last, Command("del_last"))
    dp.message.register(transactions.cmd_edit_last, Command("edit_last"))
    
    # ===== AI INPUT =====
    dp.message.register(ai_input.cmd_aiadd, Command("aiadd"))
    # Обработчик голоса (если есть)
    # dp.message.register(ai_input.handle_voice)
    # Обработчик свободного текста
    dp.message.register(ai_input.handle_free_text)
    
    # ===== REPORTS =====
    dp.message.register(reports.cmd_report_summary, Command("report"))
    dp.message.register(reports.cmd_report_balance, Command("report_balance"))
    dp.message.register(reports.cmd_report_members, Command("report_members"))
    dp.message.register(reports.cmd_report_shops, Command("report_shops"))
    dp.message.register(reports.cmd_report_export, Command("report_export"))
    
    # ===== CATEGORIES =====
    dp.message.register(categories.cmd_categories, Command("categories"))
    dp.message.register(categories.cmd_cat_add, Command("cat_add"))
    dp.message.register(categories.cmd_cat_delete, Command("cat_delete"))
    dp.message.register(categories.cmd_cat_rename, Command("cat_rename"))
    dp.message.register(categories.cmd_cat_merge, Command("cat_merge"))
    
    # ===== REMINDERS =====
    dp.message.register(reminders.cmd_reminders, Command("reminders"))
    dp.message.register(reminders.cmd_remind_add, Command("remind_add"))
    dp.message.register(reminders.cmd_remind_list, Command("remind_list"))
    
    # ===== BUDGETS =====
    dp.message.register(budgets.cmd_budget_set, Command("budget_set"))
    dp.message.register(budgets.cmd_budget_remove, Command("budget_remove"))
    dp.message.register(budgets.cmd_budget_list, Command("budget_list"))
    
    # ===== CALLBACKS =====
    dp.callback_query.register(callbacks.handle_category_selection, F.data.startswith("setcat_ai:"))
    dp.callback_query.register(callbacks.handle_category_other, F.data.startswith("setcat_ai_other:"))
    dp.callback_query.register(callbacks.handle_family_leave_confirm)
    dp.callback_query.register(callbacks.handle_reminder_paid, F.data.startswith("reminder_paid:"))
