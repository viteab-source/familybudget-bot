"""
Главный файл FastAPI приложения.
Только инициализация и подключение роутеров.
"""
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time

from .db import Base, engine, SessionLocal
from .deps import get_or_create_default_household
from .logging_config import logger

# Импортируем все роутеры
from .api import (
    users,
    households,
    categories,
    transactions,
    budgets,
    reports,
    reminders,
)

app = FastAPI(title="FamilyBudget API")


@app.on_event("startup")
def on_startup():
    """Создаём таблицы и дефолтную семью при старте."""
    logger.info("========================================")
    logger.info("🚀 Starting FamilyBudget Backend API")
    logger.info("========================================")
    
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created/verified")
    
    db = SessionLocal()
    try:
        get_or_create_default_household(db)
        logger.info("✅ Default household initialized")
    finally:
        db.close()
    
    logger.info("✅ Application startup complete")


@app.on_event("shutdown")
def on_shutdown():
    """Логируем завершение работы."""
    logger.info("👋 Shutting down FamilyBudget Backend API")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware для логирования всех HTTP запросов.
    """
    start_time = time.time()
    
    # Обрабатываем запрос
    try:
        response = await call_next(request)
        
        # Считаем время обработки
        duration = time.time() - start_time
        duration_ms = int(duration * 1000)
        
        # Логируем запрос
        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({duration_ms}ms)"
        )
        
        return response
    
    except Exception as e:
        # Логируем ошибки
        duration = time.time() - start_time
        duration_ms = int(duration * 1000)
        
        logger.error(
            f"{request.method} {request.url.path} → ERROR ({duration_ms}ms): {str(e)}"
        )
        
        # Возвращаем красивую ошибку
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


@app.get("/health")
def health_check():
    """Проверка работоспособности API."""
    return {"status": "ok"}


# ==========================================
# ПОДКЛЮЧАЕМ ВСЕ РОУТЕРЫ
# ==========================================

# Пользователи
app.include_router(users.router, prefix="/api", tags=["Users"])

# Семьи
app.include_router(households.router, prefix="/api", tags=["Households"])

# Категории
app.include_router(categories.router, prefix="/api/categories", tags=["Categories"])

# Транзакции
app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions"])

# Бюджеты
app.include_router(budgets.router, prefix="/api/budget", tags=["Budgets"])

# Отчёты
app.include_router(reports.router, prefix="/api/report", tags=["Reports"])

# Напоминания
app.include_router(reminders.router, prefix="/api/reminders", tags=["Reminders"])

logger.info("✅ All routers registered")
