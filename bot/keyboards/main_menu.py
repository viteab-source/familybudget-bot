"""Главное меню бота (persistent keyboard)"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    """
    Главное меню с 4 кнопками для вспомогательных функций.
    
    Основная функция (добавление расходов) работает БЕЗ меню:
    пользователь просто пишет текст или отправляет голос.
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 Отчёты"),
                KeyboardButton(text="🔔 Напоминания")
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="❓ Помощь")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Напишите: Магнит 500 или запишите голосом..."
    )
    return keyboard
