"""
main.py — главная точка входа FastAPI приложения.

После рефакторинга этот файл содержит только:
1. Инициализацию FastAPI
2. Подключение всех роутеров из api/*
3. Хендлер при старте приложения
4. Health check
"""

import logging
from fastapi import FastAPI

from .db import Base, engine, SessionLocal
from .api import users, transactions, categories, budgets, reminders, reports

# Настроим логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("familybudget_api")

# Создаём приложение FastAPI
app = FastAPI(
    title="FamilyBudget API",
    description="Семейный финансовый ассистент",
    version="2.0.0",
)


# -----------------------
# ИНИЦИАЛИЗАЦИЯ
# -----------------------

@app.on_event("startup")
def on_startup():
    """При старте приложения создаём таблицы БД."""
    logger.info("Создаю таблицы БД...")
    Base.metadata.create_all(bind=engine)
    
    # Создаём default household для Swagger-тестов
    db = SessionLocal()
    try:
        from .deps import get_or_create_default_household
        household = get_or_create_default_household(db)
        logger.info(f"Default household создана: {household.id}")
    finally:
        db.close()


# -----------------------
# ЗДОРОВЬЕ ПРИЛОЖЕНИЯ
# -----------------------

@app.get("/health")
def health_check():
    """Проверка здоровья приложения."""
    return {"status": "ok"}


# -----------------------
# ПОДКЛЮЧЕНИЕ РОУТЕРОВ
# -----------------------

# Пользователи и семьи
app.include_router(users.router, tags=["Users & Households"])

# Категории
app.include_router(categories.router, tags=["Categories"])

# Транзакции
app.include_router(transactions.router, tags=["Transactions"])

# Бюджеты
app.include_router(budgets.router, tags=["Budgets"])

# Напоминания
app.include_router(reminders.router, tags=["Reminders"])

# Отчёты
app.include_router(reports.router, tags=["Reports"])
