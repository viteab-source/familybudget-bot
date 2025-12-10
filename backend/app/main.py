"""
Главный файл FastAPI приложения.
Только инициализация и подключение роутеров.
"""
from fastapi import FastAPI
from .db import Base, engine, SessionLocal
from .deps import get_or_create_default_household

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
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        get_or_create_default_household(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    """Проверка работоспособности API."""
    return {"status": "ok"}


# ==========================================
# ПОДКЛЮЧАЕМ ВСЕ РОУТЕРЫ
# ==========================================

# Пользователи
app.include_router(users.router, tags=["Users"])

# Семьи
app.include_router(households.router, tags=["Households"])

# Категории
app.include_router(categories.router, prefix="/categories", tags=["Categories"])

# Транзакции
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])

# Бюджеты
app.include_router(budgets.router, prefix="/budget", tags=["Budgets"])

# Отчёты
app.include_router(reports.router, prefix="/report", tags=["Reports"])

# Напоминания
app.include_router(reminders.router, prefix="/reminders", tags=["Reminders"])
