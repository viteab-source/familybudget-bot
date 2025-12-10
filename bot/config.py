"""
Конфигурация бота.
Все настройки и переменные окружения.
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

# URL Backend API
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# Yandex API (для STT и YandexGPT)
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

# Настройки логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
