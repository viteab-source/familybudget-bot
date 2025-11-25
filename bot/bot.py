import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

    # Создаём объекты бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Команда /start
    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! 👋\n"
            "Я FamilyBudget Bot.\n\n"
            "Пока я умею только отвечать на /start и /help.\n"
            "Чуть позже научимся добавлять расходы и показывать отчёты 🙂"
        )

    # Команда /help
    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "Доступные команды:\n"
            "/start — начать работу\n"
            "/help — помощь\n"
            "/add — (скоро) добавить расход\n"
            "/report — (скоро) показать отчёт"
        )

    print("Бот запущен. Нажми Ctrl+C, чтобы остановить.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
