"""
Главный файл Telegram бота.
Только инициализация и подключение handlers.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import BOT_TOKEN
from .handlers import (
    base,
    user_family,
    transactions,
    categories,
    budgets,
    reports,
    reminders,
)


# ==========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("familybudget.bot")


# ==========================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ==========================================

def create_bot() -> Bot:
    """Создаёт экземпляр бота."""
    return Bot(token=BOT_TOKEN)


def create_dispatcher() -> Dispatcher:
    """Создаёт диспетчер и подключает все handlers."""
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключаем все роутеры
    dp.include_router(base.router)
    dp.include_router(user_family.router)
    dp.include_router(transactions.router)
    dp.include_router(categories.router)
    dp.include_router(budgets.router)
    dp.include_router(reports.router)
    dp.include_router(reminders.router)
    
    logger.info("✅ All handlers registered")
    
    return dp


# ==========================================
# ЗАПУСК БОТА
# ==========================================

async def main():
    """Главная функция запуска."""
    logger.info("========================================")
    logger.info("🤖 Starting FamilyBudget Telegram Bot")
    logger.info("========================================")
    
    bot = create_bot()
    dp = create_dispatcher()
    
    logger.info("✅ Bot initialized")
    logger.info("✅ Starting polling...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("👋 Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Bot stopped by user (Ctrl+C)")
