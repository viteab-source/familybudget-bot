"""
bot/main.py — Инициализация бота и запуск
"""

import asyncio
import logging

from .config import bot, dp, logger
from . import handlers


async def main():
    """Инициализируем бота и запускаем polling."""
    
    logger.info("🤖 Starting FamilyBudget Bot...")
    
    # Подключаем все handlers
    handlers.setup(dp)
    
    try:
        # Запускаем polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Error in bot polling: {e}", exc_info=True)
    finally:
        logger.info("🛑 Bot stopped.")
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
