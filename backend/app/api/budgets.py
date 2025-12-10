"""
Эндпоинты для работы с бюджетами по категориям.
"""
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..db import get_db
from ..deps import get_or_create_user_and_household

router = APIRouter()


@router.post("/set")
def set_budget(
    category_name: str = Query(..., description="Название категории"),
    limit_amount: float = Query(..., gt=0, description="Лимит бюджета на месяц"),
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Задать/обновить лимит бюджета для категории на текущий месяц.
    
    Пример:
    POST /budget/set?telegram_id=123456789&category_name=Продукты&limit_amount=50000
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    category_name = category_name.strip()
    if not category_name:
        raise HTTPException(
            status_code=400,
            detail="Название категории не может быть пустым",
        )

    # Ищем или создаём категорию
    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == category_name,
        )
        .first()
    )

    if not category:
        category = models.Category(
            household_id=household.id,
            name=category_name,
        )
        db.add(category)
        db.commit()
        db.refresh(category)

    # Текущий месяц в формате YYYY-MM
    period_month = datetime.utcnow().strftime("%Y-%m")

    # Ищем существующий бюджет
    budget = (
        db.query(models.CategoryBudget)
        .filter(
            models.CategoryBudget.household_id == household.id,
            models.CategoryBudget.category_id == category.id,
            models.CategoryBudget.period_month == period_month,
        )
        .first()
    )

    if budget:
        # Обновляем существующий
        budget.limit_amount = limit_amount
    else:
        # Создаём новый
        budget = models.CategoryBudget(
            household_id=household.id,
            category_id=category.id,
            period_month=period_month,
            limit_amount=limit_amount,
        )
        db.add(budget)

    db.commit()

    return {
        "status": "ok",
        "category": category_name,
        "limit": float(limit_amount),
        "period": period_month,
    }


@router.get("/status")
def get_budget_status(
    telegram_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Статус бюджетов: по каждой категории считает:
    - limit — лимит
    - spent — потрачено
    - percent — процент от лимита
    
    Пример:
    GET /budget/status?telegram_id=123456789
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    # Текущий месяц
    now = datetime.utcnow()
    period_month = now.strftime("%Y-%m")
    
    # Границы месяца
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)

    # Все бюджеты семьи на текущий месяц
    budgets = (
        db.query(models.CategoryBudget)
        .filter(
            models.CategoryBudget.household_id == household.id,
            models.CategoryBudget.period_month == period_month,
        )
        .all()
    )

    result = []

    for budget in budgets:
        category = budget.category
        if not category:
            continue

        # Считаем потраченное по категории за месяц
        spent = (
            db.query(func.sum(models.Transaction.amount))
            .filter(
                models.Transaction.household_id == household.id,
                models.Transaction.category_id == category.id,
                models.Transaction.kind == "expense",
                models.Transaction.date >= month_start,
                models.Transaction.date < next_month_start,
            )
            .scalar()
            or 0
        )

        limit_val = float(budget.limit_amount or 0)
        spent_val = float(spent)
        percent = (spent_val / limit_val * 100) if limit_val > 0 else 0.0

        result.append({
            "category": category.name,
            "limit": limit_val,
            "spent": spent_val,
            "percent": round(percent, 1),
            "currency": household.currency,
        })

    # Сортируем по проценту (самые "красные" сначала)
    result.sort(key=lambda x: x["percent"], reverse=True)

    return {
        "period": period_month,
        "budgets": result,
    }
