import logging
import time
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware  # <--- ВОТ ВАЖНЫЙ ИМПОРТ
from starlette.responses import Response

# Импорты из твоего проекта
from app.api import users, transactions, categories, budgets, reports, reminders
from app.db import Base, engine
from app import ai

# ========================
# ЛОГИРОВАНИЕ (БАГ ФИХ #2)
# ========================

# Создаём папку для логов если её нет
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/api.log'),  # Пишем в файл
        logging.StreamHandler()  # И в консоль
    ]
)

logger = logging.getLogger(__name__)

# Middleware для логирования всех запросов
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Логируем входящий запрос
        logger.info(f"🔵 {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            
            # Логируем исходящий ответ
            duration = time.time() - start_time
            status_emoji = "✅" if response.status_code < 400 else "⚠️"
            logger.info(
                f"{status_emoji} {request.method} {request.url.path} "
                f"→ {response.status_code} ({duration:.2f}s)"
            )
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"❌ {request.method} {request.url.path} "
                f"→ ERROR: {str(e)} ({duration:.2f}s)",
                exc_info=True
            )
            raise

# ========================
# ИНИЦИАЛИЗАЦИЯ APP
# ========================

# Создаем таблицы в БД (для dev режима)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FamilyBudget Bot API",
    description="API для учёта семейных расходов",
    version="2.0.0"
)

# Добавляем middleware логирования
app.add_middleware(LoggingMiddleware)

# Подключаем роутеры
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(categories.router, prefix="/categories", tags=["Categories"])
app.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(reminders.router, prefix="/reminders", tags=["Reminders"])

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}

@app.get("/")
def root():
    return {"message": "FamilyBudget API is running. Go to /docs for Swagger UI."}
