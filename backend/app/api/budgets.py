"""
api/budgets.py — Эндпоинты для бюджетов.
POST /budget/set — установить лимит
GET /budget/status — статус по категориям
"""

from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas
from ..deps import get_or_create_user_and_household

router = APIRouter()


@router.post("/budget/set")
def set_budget(
    body: dict,  # {"category": "Продукты", "limit_amount": 10000, "period_month": "2025-12"}
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Установить месячный лимит бюджета для категории.
    
    Пример:
    {
        "category": "Продукты",
        "limit_amount": 10000,
        "period_month": "2025-12"  # опционально, по умолчанию текущий месяц
    }
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    cat_name = (body.get("category") or "").strip()
    if not cat_name:
        raise HTTPException(
            status_code=400,
            detail="Категория не может быть пустой",
        )

    limit_amount = body.get("limit_amount")
    if limit_amount is None or float(limit_amount) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Лимит должен быть больше 0",
        )

    # Определяем период (текущий месяц, если не указан)
    period_month = body.get("period_month")
    if not period_month:
        now = datetime.utcnow()
        period_month = now.strftime("%Y-%m")

    # Ищем или создаём категорию
    category = (
        db.query(models.Category)
        .filter(
            models.Category.household_id == household.id,
            models.Category.name == cat_name,
        )
        .first()
    )

    if not category:
        category = models.Category(
            household_id=household.id,
            name=cat_name,
        )
        db.add(category)
        db.commit()
        db.refresh(category)

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
        budget.limit_amount = float(limit_amount)
        db.commit()
    else:
        # Создаём новый
        budget = models.CategoryBudget(
            household_id=household.id,
            category_id=category.id,
            limit_amount=float(limit_amount),
            period_month=period_month,
        )
        db.add(budget)
        db.commit()

    return {"status": "ok", "category": cat_name, "limit": float(limit_amount), "period": period_month}


@router.get("/budget/status")
def get_budget_status(
    db: Session = Depends(get_db),
    telegram_id: int | None = Query(default=None),
):
    """
    Получить статус всех бюджетов для текущего месяца.
    
    Возвращает для каждой категории:
    - лимит
    - потрачено
    - процент
    """
    user, household = get_or_create_user_and_household(db, telegram_id)

    now = datetime.utcnow()
    period_month = now.strftime("%Y-%m")

    # Границы месяца
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)

    # Берём все бюджеты на текущий месяц
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
        # Считаем потраченное за месяц
        spent = (
            db.query(func.sum(models.Transaction.amount))
            .filter(
                models.Transaction.household_id == household.id,
                models.Transaction.category_id == budget.category_id,
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

        category = budget.category
        result.append({
            "category": category.name if category else "Unknown",
            "category_id": budget.category_id,
            "limit": limit_val,
            "spent": spent_val,
            "percent": round(percent, 1),
        })

    return {
        "period": period_month,
        "budgets": result,
    }
