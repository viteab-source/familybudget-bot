"""
bot/config.py — Конфигурация бота, импорты, логирование
"""

import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher

# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("familybudget_bot")

# Конфиг
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

# Инициализируем бота и диспетчер
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logger.info("==== FamilyBudget Bot Configuration ====")
logger.info(f"API_BASE_URL = {API_BASE_URL}")
logger.info(f"BOT_TOKEN = {BOT_TOKEN[:10]}...")
