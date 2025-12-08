"""
api/__init__.py — инициализация пакета api.

Здесь мы импортируем все роутеры, чтобы их было легко подключить в main.py
"""

from . import users, transactions, categories, budgets, reminders, reports

__all__ = ["users", "transactions", "categories", "budgets", "reminders", "reports"]
