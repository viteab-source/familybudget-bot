"""
bot/cache.py — Глобальные переменные и кэши
"""

import asyncio

# Пользователь нажал "Нет подходящей категории" и мы ждём от него текст
# telegram_id -> {"tx_id": int}
pending_manual_category = {}

# Кэш подсказок категорий по ИИ, чтобы потом залогировать выбор
# (telegram_id, tx_id) -> {...}
ai_suggestions_cache = {}

# Пользователи, которые сейчас подтверждают выход из семьи
pending_family_leave_confirmations: set[int] = set()


async def _clear_family_leave_confirmation(user_id: int, delay_seconds: int = 60):
    """
    Через delay_seconds секунд убираем запрос на подтверждение,
    если пользователь ничего не сделал.
    """
    await asyncio.sleep(delay_seconds)
    pending_family_leave_confirmations.discard(user_id)
